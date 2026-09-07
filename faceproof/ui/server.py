"""Loopback HTTP server for the dashboard - stdlib only, no new dependencies.

Why ``http.server`` and not FastAPI: this repository's ``pyproject`` extras and
``requirements.lock.txt`` are pinned and CI is green against them.  A demo
dashboard is not worth reopening dependency resolution, and the stdlib is
sufficient - the API is seven JSON endpoints and a static file.

Security posture (this serves a local demo, but it still touches a funded
testnet key):

* binds ``127.0.0.1`` only, and rejects requests whose ``Host`` is not loopback,
  which is what stops a browser on another origin from driving the pipeline;
* ``PRIVATE_KEY`` is never accepted from, or returned to, the client - the
  anchor step reads it from the process environment exactly as the CLI does;
* config is exposed through ``cfg.public()``, which masks secrets;
* artifacts are served from a fixed filename whitelist under ``out/`` with the
  resolved path re-checked against ``out/``, so no traversal is possible.
"""

from __future__ import annotations

import json
import mimetypes
import os
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qs, urlparse

from faceproof.ui import pipeline as P

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_PORT = 8765


# --------------------------------------------------------------------------- #
# read-only state the dashboard opens with
# --------------------------------------------------------------------------- #


def _calibration() -> Dict[str, Any]:
    from faceproof.config import cfg

    path = cfg.calibration_json
    if not path.exists():
        return {"present": False,
                "note": "no calibration measured - the 0.55 placeholder is in force",
                "accept_at": cfg.accept_at}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"present": False, "error": str(exc), "accept_at": cfg.accept_at}
    data["present"] = True
    data["in_force"] = cfg.accept_at
    data["env_override"] = os.environ.get("FACEPROOF_ACCEPT_AT") is not None
    return data


def _index_state() -> Dict[str, Any]:
    try:
        from faceproof.stage2_bridge import _faiss_available, _index_present, index_stats

        return {"present": _index_present(), "faiss": _faiss_available(),
                "snapshot": index_stats()}
    except Exception as exc:
        return {"present": False, "faiss": False, "snapshot": None, "error": str(exc)}


def _chain_state() -> Dict[str, Any]:
    """Which chain the anchor step would use - presence of secrets only."""
    from faceproof.config import cfg

    out: Dict[str, Any] = {
        "chain": os.environ.get("CHAIN", "anvil"),
        # NB: the anchor reads REGISTRY_ADDRESS (faceproof.chain.registry_address);
        # CONTRACT_ADDRESS is not consulted anywhere and reporting it here made
        # the dashboard show an empty contract while a real one was configured.
        "contract": (os.environ.get("REGISTRY_ADDRESS")
                     or os.environ.get("FACEPROOF_REGISTRY_ADDRESS") or ""),
        "rpc_configured": bool(os.environ.get("RPC_URL")),
        "private_key_present": bool(os.environ.get("PRIVATE_KEY")),
        "serpapi_key_present": bool(os.environ.get("SERPAPI_KEY")),
        "accept_at": cfg.accept_at,
    }
    try:
        from faceproof.chain import CHAINS, chain_name

        name = chain_name()
        out["chain"] = name
        out["chain_id"] = CHAINS.get(name, {}).get("chain_id")
    except Exception:
        pass
    return out


def _runs() -> list[Dict[str, Any]]:
    from faceproof.config import cfg

    if not cfg.out_dir.exists():
        return []
    out = []
    for d in sorted(cfg.out_dir.glob("run-*"), key=lambda p: p.stat().st_mtime, reverse=True):
        files = {name for name in P.ARTIFACTS if (d / name).is_file()}
        outcome = "incomplete"
        if "bundle.json" in files:
            outcome = "anchored" if "receipt.json" in files else "bundle"
        elif "abstain.json" in files:
            outcome = "abstain"
        elif "probe.json" in files:
            outcome = "probe-only"
        out.append({
            "run_id": d.name.removeprefix("run-"),
            "run_dir": d.as_posix(),
            "mtime": d.stat().st_mtime,
            "outcome": outcome,
            "files": sorted(files),
        })
    return out


def build_app_state() -> Dict[str, Any]:
    """Everything the dashboard needs on load. Read-only; runs nothing."""
    from faceproof.config import cfg

    demo_image = cfg.data_dir / "demo" / "synthetic_face.jpg"
    return {
        "config": cfg.public(),
        "calibration": _calibration(),
        "index": _index_state(),
        "chain": _chain_state(),
        "runs": _runs(),
        "busy": P.REGISTRY.busy(),
        "steps": list(P.STEPS),
        "demo_image": demo_image.as_posix() if demo_image.exists() else None,
        "subjects": _subjects(),
    }


def _subjects() -> list[Dict[str, Any]]:
    """Consented subjects via ``ConsentRecord.public()`` - never the salt."""
    try:
        from faceproof.consent import ConsentStore, check as consent_check
        from faceproof.config import cfg

        rows = []
        for rec in ConsentStore().list():
            ok, reason = consent_check(rec, scope=cfg.consent_scope)
            row = {"subject_id": rec.subject_id, "valid": ok, "reason": reason}
            row.update(rec.public())            # scope/granted/expires/commitment
            rows.append(row)
        return rows
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# request handling
# --------------------------------------------------------------------------- #


class _Handler(BaseHTTPRequestHandler):
    server_version = "FaceProofUI/1.0"
    protocol_version = "HTTP/1.1"

    # ---- plumbing ------------------------------------------------------ #
    def log_message(self, fmt: str, *args: Any) -> None:      # quieter console
        pass

    def _host_is_local(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in ("127.0.0.1", "localhost", "::1", "")

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        # the page is entirely self-hosted: no external script, style or font
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; "
                         "script-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "connect-src 'self'")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj: Any, code: int = 200) -> None:
        self._send(code, json.dumps(obj, default=str).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _error(self, code: int, message: str) -> None:
        self._json({"error": message}, code)

    def _body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8")) or {}
        except (ValueError, UnicodeDecodeError):
            return {}

    # ---- routing ------------------------------------------------------- #
    def do_GET(self) -> None:      # noqa: N802
        if not self._host_is_local():
            return self._error(403, "loopback only")
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        try:
            if path.startswith("/api/"):
                return self._api_get(path, query)
            return self._static(path)
        except Exception as exc:
            return self._error(500, f"{type(exc).__name__}: {exc}")

    do_HEAD = do_GET

    def do_POST(self) -> None:     # noqa: N802
        if not self._host_is_local():
            return self._error(403, "loopback only")
        path = urlparse(self.path).path
        try:
            return self._api_post(path, self._body())
        except Exception as exc:
            return self._error(500, f"{type(exc).__name__}: {exc}")

    # ---- static -------------------------------------------------------- #
    def _static(self, path: str) -> None:
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (STATIC_DIR / rel).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.is_file():
            return self._error(404, "not found")
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    # ---- GET api ------------------------------------------------------- #
    def _api_get(self, path: str, query: Dict[str, list]) -> None:
        if path == "/api/state":
            return self._json(build_app_state())

        if path == "/api/job":
            job = P.REGISTRY.get((query.get("id") or [""])[0])
            if job is None:
                return self._error(404, "no such job")
            cursor = int((query.get("cursor") or ["0"])[0])
            snap = job.snapshot()
            snap["lines"] = job.since(cursor)
            return self._json(snap)

        if path == "/api/jobs":
            return self._json({"jobs": P.REGISTRY.recent(), "busy": P.REGISTRY.busy()})

        if path == "/api/run":
            run_dir = self._run_dir((query.get("id") or [""])[0])
            if run_dir is None:
                return self._error(404, "no such run")
            return self._json(P.collect_run(run_dir))

        if path == "/api/probe-image":
            run_dir = self._run_dir((query.get("id") or [""])[0])
            if run_dir is None:
                return self._error(404, "no such run")
            img = P.probe_image_for(run_dir)
            if img is None:
                return self._error(404, "no probe image retained for this run")
            return self._image(img)

        if path == "/api/corpus-image":
            # Content-addressed: the client sends a digest, never a path. The
            # path comes from our own sidecar and is re-checked to live under
            # data/, so this cannot be turned into an arbitrary file read.
            digest = (query.get("sha256") or [""])[0].lower()
            if len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
                return self._error(400, "sha256 must be 64 hex characters")
            from faceproof.config import cfg
            from faceproof.local_corpus import probe_is_in_index

            row = probe_is_in_index(digest)
            if not row or not row.get("local_image"):
                return self._error(404, "no indexed image with that digest")
            target = (Path(row["local_image"]) if Path(row["local_image"]).is_absolute()
                      else _REPO_ROOT / row["local_image"]).resolve()
            if not str(target).startswith(str(cfg.data_dir.resolve())) or not target.is_file():
                return self._error(404, "not found")
            return self._image(target)

        if path == "/api/artifact":
            run_dir = self._run_dir((query.get("id") or [""])[0])
            name = (query.get("name") or [""])[0]
            if run_dir is None or name not in P.ARTIFACTS:
                return self._error(404, "not found")
            target = (run_dir / name).resolve()
            if not target.is_file():
                return self._error(404, "not found")
            return self._send(200, target.read_bytes(), "text/plain; charset=utf-8")

        if path == "/api/probe-image":
            run_dir = self._run_dir((query.get("id") or [""])[0])
            if run_dir is None:
                return self._error(404, "not found")
            target = P._probe_image_path(run_dir)
            if target is None:
                return self._error(404, "probe image unavailable")
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            return self._send(200, target.read_bytes(), ctype)

        return self._error(404, "unknown endpoint")

    def _image(self, target: Path) -> None:
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if not ctype.startswith("image/"):
            return self._error(415, "not an image")
        self._send(200, target.read_bytes(), ctype)

    @staticmethod
    def _run_dir(run_id: str) -> Optional[Path]:
        """Resolve a run id under ``out/`` - rejects traversal and absolutes."""
        from faceproof.config import cfg

        if not run_id or "/" in run_id or "\\" in run_id or ".." in run_id:
            return None
        base = cfg.out_dir.resolve()
        candidate = (base / f"run-{run_id}").resolve()
        if not str(candidate).startswith(str(base)) or not candidate.is_dir():
            return None
        return candidate

    # ---- POST api ------------------------------------------------------ #
    def _api_post(self, path: str, body: Dict[str, Any]) -> None:
        from faceproof.config import cfg

        if path == "/api/pipeline":
            if P.REGISTRY.busy():
                return self._error(409, "a run is already in progress")

            image = str(body.get("image") or "").strip()
            subject = str(body.get("subject") or "").strip()
            if not image or not subject:
                return self._error(400, "image and subject are required")
            if not Path(image).is_file():
                return self._error(400, f"image not found: {image}")

            opts = dict(
                image=image,
                subject=subject,
                use_real_stage2=bool(body.get("real_stage2", True)),
                allow_synthetic=bool(body.get("demo", False)),
                do_anchor=bool(body.get("anchor", False)),
                do_tamper=bool(body.get("tamper", True)),
                check_chain=bool(body.get("check_chain", True)),
            )
            job = P.REGISTRY.start(
                "pipeline", lambda j: P.run_pipeline(j, **opts))
            return self._json({"job_id": job.id})

        if path == "/api/verify":
            run_dir = self._run_dir(str(body.get("run_id") or ""))
            if run_dir is None:
                return self._error(404, "no such run")
            check_chain = bool(body.get("check_chain", True))

            def _verify(job: P.Job) -> None:
                from faceproof.verify import verify_run

                job.step("verify", "running")
                ok = verify_run(run_dir, check_chain=check_chain)
                job.result["verification"] = P.verification_rows(
                    run_dir, check_chain=check_chain)
                job.result["verified"] = ok
                job.result["run_id"] = run_dir.name.removeprefix("run-")
                job.step("verify", "pass" if ok else "fail", verified=ok)

            return self._json({"job_id": P.REGISTRY.start("verify", _verify).id})

        if path == "/api/tamper":
            run_dir = self._run_dir(str(body.get("run_id") or ""))
            if run_dir is None:
                return self._error(404, "no such run")

            def _tamper(job: P.Job) -> None:
                from faceproof.verify import tamper_demonstration

                job.step("tamper", "running")
                original_ok, detected = tamper_demonstration(run_dir)
                job.result.update(original_passed=original_ok, tamper_detected=detected,
                                  run_id=run_dir.name.removeprefix("run-"))
                job.step("tamper", "pass" if detected else "fail",
                         original_passed=original_ok, tamper_detected=detected)

            return self._json({"job_id": P.REGISTRY.start("tamper", _tamper).id})

        if path == "/api/anchor":
            run_dir = self._run_dir(str(body.get("run_id") or ""))
            if run_dir is None:
                return self._error(404, "no such run")

            def _anchor_job(job: P.Job) -> None:
                from faceproof.anchor import anchor as _anchor

                job.step("anchor", "running")
                receipt = _anchor(run_dir)      # reads PRIVATE_KEY from the env
                job.result["receipt"] = receipt
                job.result["run_id"] = run_dir.name.removeprefix("run-")
                job.step("anchor", "pass", **receipt)

            return self._json({"job_id": P.REGISTRY.start("anchor", _anchor_job).id})

        if path == "/api/corpus":
            handles = [h for h in (body.get("handles") or []) if str(h).strip()]
            limit = body.get("limit")

            def _corpus(job: P.Job) -> None:
                from faceproof import stage2_corpus as sc

                if handles:
                    job.emit(f"[corpus] ingesting {len(handles)} handle(s)")
                    sc.ingest(handles)
                records, stats = sc.fetch_images(
                    limit=int(limit) if limit else None, log=job.emit)
                job.emit(f"[corpus] fetch {stats}")
                summary = sc.build_index(records)
                job.result.update(stats=stats, summary=summary)

            return self._json({"job_id": P.REGISTRY.start("corpus", _corpus).id})

        if path == "/api/consent":
            action = str(body.get("action") or "")
            subject = str(body.get("subject") or "").strip()
            if not subject:
                return self._error(400, "subject is required")
            from faceproof.cli import cmd_consent_grant, cmd_consent_revoke

            def _consent(job: P.Job) -> None:
                if action == "grant":
                    code = cmd_consent_grant(subject, None, None)
                elif action == "revoke":
                    code = cmd_consent_revoke(subject)
                else:
                    raise ValueError(f"unknown consent action {action!r}")
                job.result.update(action=action, subject=subject, exit_code=code)

            return self._json({"job_id": P.REGISTRY.start("consent", _consent).id})

        return self._error(404, "unknown endpoint")


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #


def _free_port(start: int, tries: int = 20) -> int:
    for port in range(start, start + tries):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


def serve(port: int = DEFAULT_PORT, *, open_browser: bool = True,
          host: str = "127.0.0.1") -> int:
    """Run the dashboard until interrupted. Returns a process exit code."""
    port = _free_port(port)
    httpd = ThreadingHTTPServer((host, port), _Handler)
    url = f"http://{host}:{port}/"

    print(f"FaceProof dashboard  {url}")
    print("  loopback only - Ctrl+C to stop")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
    return 0
