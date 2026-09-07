"""Job runner behind the dashboard - it drives the real pipeline, nothing else.

Every step below is a call into a module that already exists and is already
tested.  This file contributes ordering, log capture and a JSON-shaped record
of what each stage actually returned; it contributes **no** matching, hashing,
Merkle or chain logic of its own.  The order mirrors ``faceproof.run.cmd_search``
so the dashboard and the CLI cannot drift apart:

    cli.cmd_probe -> stage2_bridge.run_stage2 -> stage2_adapter.load_stage2
                  -> bundle.assemble_bundle   -> anchor.anchor
                  -> verify.verify_run        -> verify.tamper_demonstration

Honesty rules enforced here:

* a stage that abstains ends the run as ``ABSTAIN``; no later stage is faked;
* the synthetic Stage 2 fixture is reachable only via an explicit ``demo``
  flag and is reported with ``"synthetic": true`` so the UI can label it;
* a step that raises is recorded as ``error`` - never quietly downgraded to a
  pass.
"""

from __future__ import annotations

import io
import json
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Steps the dashboard renders as a progress rail, in order.
STEPS: tuple[str, ...] = (
    "consent",
    "stage1",
    "stage2",
    "stage3",
    "anchor",
    "verify",
    "tamper",
)

# Artifacts a client may read back from a run directory.  A whitelist, so a
# crafted run_id can never be used to read arbitrary files off the machine.
ARTIFACTS: tuple[str, ...] = (
    "probe.json",
    "stage2.json",
    "bundle.json",
    "proofs.json",
    "receipt.json",
    "abstain.json",
    "manifest.jsonl",
    # the probe photograph, retained by the dashboard runner so the run is
    # self-describing and the image can be shown without a filesystem endpoint
    "probe_image.jpg",
    "probe_image.jpeg",
    "probe_image.png",
    "probe_image.webp",
    "probe_image.bmp",
)

#: Whitelisted artifact names that are images rather than JSON.
IMAGE_ARTIFACTS = tuple(n for n in ARTIFACTS if n.startswith("probe_image."))


def retain_probe_image(run_dir, image):
    """Copy the probe photograph into the run directory.

    Person 1's Stage 1 records the image filename and SHA-256 but not its
    path, so nothing downstream can locate the original.  Rather than add a
    filesystem-serving endpoint to the dashboard (which would be able to read
    anything on the machine), the runner copies the file into the run it
    belongs to, where the existing artifact whitelist already governs access.
    """
    import shutil
    from pathlib import Path as _P

    src = _P(image)
    suffix = src.suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        return None
    dest = _P(run_dir) / ("probe_image" + suffix)
    try:
        shutil.copy2(src, dest)
    except OSError:
        return None
    return dest


# --------------------------------------------------------------------------- #
# job bookkeeping
# --------------------------------------------------------------------------- #


@dataclass
class Job:
    """One dashboard run: a log stream plus a growing result document."""

    id: str
    kind: str
    status: str = "running"              # running | done | error
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    lines: List[Dict[str, Any]] = field(default_factory=list)
    steps: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    result: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # ---- log stream -------------------------------------------------- #
    def emit(self, text: str, level: str = "info") -> None:
        for raw in str(text).splitlines() or [""]:
            with self._lock:
                self.lines.append({
                    "seq": len(self.lines),
                    "t": round(time.time() - self.started_at, 3),
                    "level": level,
                    "text": raw.rstrip(),
                })

    def since(self, cursor: int) -> List[Dict[str, Any]]:
        with self._lock:
            return self.lines[max(0, cursor):]

    # ---- step state --------------------------------------------------- #
    def step(self, name: str, status: str, **detail: Any) -> None:
        """Record a step outcome. ``status`` is one of the UI's own vocabulary."""
        with self._lock:
            entry = self.steps.setdefault(name, {"name": name})
            entry["status"] = status
            entry.update(detail)

    def snapshot(self, cursor: int = 0) -> Dict[str, Any]:
        with self._lock:
            steps = [self.steps.get(s, {"name": s, "status": "pending"}) for s in STEPS]
            return {
                "id": self.id,
                "kind": self.kind,
                "status": self.status,
                "elapsed": round((self.ended_at or time.time()) - self.started_at, 2),
                "steps": steps,
                "result": self.result,
                "error": self.error,
                "cursor": len(self.lines),
            }


class _Tee(io.TextIOBase):
    """stdout replacement that mirrors console output into a job's log stream.

    ``rich.Console`` resolves ``sys.stdout`` lazily on every write, so the
    stage modules' existing consoles land here without being reconfigured -
    the dashboard shows exactly the text the CLI would have shown.
    """

    def __init__(self, job: Job, mirror: Any) -> None:
        self._job, self._mirror, self._buf = job, mirror, ""

    def write(self, s: str) -> int:  # noqa: D102
        try:
            self._mirror.write(s)
        except Exception:
            pass
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._job.emit(line)
        return len(s)

    def flush(self) -> None:  # noqa: D102
        if self._buf:
            self._job.emit(self._buf)
            self._buf = ""
        try:
            self._mirror.flush()
        except Exception:
            pass

    def isatty(self) -> bool:
        # False -> rich emits plain text, which is what the browser wants.
        return False


class JobRegistry:
    """In-memory job store.  One pipeline at a time: runs share out/ and data/."""

    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self._busy = threading.Lock()

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def recent(self, n: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.started_at, reverse=True)
        return [{"id": j.id, "kind": j.kind, "status": j.status,
                 "started_at": j.started_at} for j in jobs[:n]]

    def busy(self) -> bool:
        return self._busy.locked()

    def start(self, kind: str, target: Callable[[Job], None]) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind)
        with self._lock:
            self._jobs[job.id] = job

        def runner() -> None:
            import sys

            if not self._busy.acquire(blocking=False):
                job.status = "error"
                job.error = "another run is already in progress"
                job.ended_at = time.time()
                return
            saved_out, saved_err = sys.stdout, sys.stderr
            tee = _Tee(job, saved_out)
            sys.stdout = sys.stderr = tee
            try:
                target(job)
                if job.status == "running":
                    job.status = "done"
            except Exception as exc:
                job.status = "error"
                job.error = f"{type(exc).__name__}: {exc}"
                job.emit(job.error, level="error")
                job.emit(traceback.format_exc(), level="error")
            finally:
                tee.flush()
                sys.stdout, sys.stderr = saved_out, saved_err
                job.ended_at = time.time()
                self._busy.release()

        threading.Thread(target=runner, daemon=True, name=f"job-{job.id}").start()
        return job


REGISTRY = JobRegistry()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def read_artifact(run_dir: Path, name: str) -> Optional[Any]:
    """Parsed artifact, or None when the stage did not produce it."""
    path = Path(run_dir) / name
    if not path.exists():
        return None
    if name in IMAGE_ARTIFACTS:
        # binary; the dashboard fetches these through /api/probe-image
        return {"file": name, "bytes": path.stat().st_size}
    text = path.read_text(encoding="utf-8")
    if name.endswith(".jsonl"):
        out = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    out.append({"raw": line})
        return out
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}

def _probe_image_path(run_dir: Path) -> Optional[Path]:
    """Return the hash-checked source image when it is under data/."""
    probe = read_artifact(run_dir, "probe.json") or {}
    filename = ((probe.get("image") or {}).get("filename") or "")
    digest = ((probe.get("image") or {}).get("sha256") or "").lower()
    if not filename or Path(filename).name != filename or len(digest) != 64:
        return None
    from faceproof.config import cfg
    import hashlib
    for candidate in cfg.data_dir.rglob(filename):
        if candidate.is_file():
            h = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if h == digest:
                return candidate
    return None


def probe_image_for(run_dir: Path) -> Optional[Path]:
    """The probe photograph for a run, or None.

    Two sources, in order: the copy the dashboard runner retained inside the
    run directory, then a hash-verified search under ``data/`` for runs made
    from the CLI (which does not retain one).  Both are content-checked or
    self-produced, so neither turns into an arbitrary file read.
    """
    run_path = Path(run_dir)
    for name in IMAGE_ARTIFACTS:
        candidate = run_path / name
        if candidate.is_file():
            return candidate
    return _probe_image_path(run_path)


def collect_run(run_dir: Path) -> Dict[str, Any]:
    """Everything the dashboard knows about a run - read from disk, not memory."""
    run_path = Path(run_dir)
    artifacts = {name: read_artifact(run_path, name) for name in ARTIFACTS}
    present = [n for n, v in artifacts.items() if v is not None]
    return {
        "run_id": run_path.name.removeprefix("run-"),
        "run_dir": run_path.as_posix(),
        "artifacts": artifacts,
        "present": present,
        "files": sorted(name for name in ARTIFACTS
                         if (run_path / name).is_file()),
        "probe_image": probe_image_for(run_path) is not None,
    }


def verification_rows(run_dir: Path, *, check_chain: bool) -> Dict[str, Any]:
    """Structured re-verification detail to sit beside ``verify_run``'s verdict.

    The authoritative pass/fail stays :func:`faceproof.verify.verify_run`; this
    only re-reads the same recomputation so the UI can show a per-row table
    instead of a single boolean.
    """
    from faceproof.verify import _check_chain, _load, verify_bundle_locally

    bundle, proofs, receipt = _load(run_dir)
    local = verify_bundle_locally(bundle, proofs)

    want_chain = bool(check_chain and receipt and receipt.get("contract"))
    chain: Dict[str, Any] = {"chain_root_match": None, "chain_verify_field": None}
    chain_error: Optional[str] = None
    if want_chain:
        try:
            chain = _check_chain(bundle, proofs, receipt, local)
        except Exception as exc:
            chain_error = str(exc)

    def chain_cell(v: Optional[bool]) -> Optional[bool]:
        if not want_chain:
            return None
        return False if chain_error is not None else (v is True)

    rows = [
        {"check": "recomputed root", "value": local["derived_root"], "ok": None},
        {"check": "== stored root", "value": str(local["stored_root"]),
         "ok": local["root_match"]},
        {"check": "selective disclosure (tree rebuilt)", "value": "match_location",
         "ok": local["selective_disclosure_regenerated"]},
        {"check": "match_location leaf under anchored root", "value": "proofs.json",
         "ok": local["selective_disclosure_stored_proof"]},
        {"check": "== on-chain root", "value": "EvidenceRegistry.get()",
         "ok": chain_cell(chain["chain_root_match"])},
        {"check": "on-chain verifyField()", "value": "match_location",
         "ok": chain_cell(chain["chain_verify_field"])},
    ]
    return {
        "rows": rows,
        "leaves": local["leaves"],
        "derived_root": local["derived_root"],
        "stored_root": local["stored_root"],
        "chain_checked": want_chain,
        "chain_error": chain_error,
    }


# --------------------------------------------------------------------------- #
# the pipeline job
# --------------------------------------------------------------------------- #


def run_pipeline(job: Job, *, image: str, subject: str, use_real_stage2: bool = True,
                 allow_synthetic: bool = False, do_anchor: bool = False,
                 do_tamper: bool = True, check_chain: bool = True) -> None:
    """Stage 1 -> Stage 2 -> Stage 3 -> anchor -> verify -> tamper, for real."""
    from faceproof.bundle import AbstainError, assemble_bundle, recompute_root, write_abstain
    from faceproof.config import cfg
    from faceproof.handoff import load_record
    from faceproof.stage2_adapter import Stage2ResultMissing, load_stage2

    res = job.result
    res["params"] = {
        "image": image, "subject": subject, "real_stage2": use_real_stage2,
        "allow_synthetic": allow_synthetic, "anchor": do_anchor,
        "accept_at": cfg.accept_at,
    }

    # ---- Stage 1 (Person 1, unmodified) -------------------------------- #
    job.step("consent", "running")
    job.step("stage1", "running")
    job.emit(f"[stage 1] probing {image} for subject {subject!r}")

    from faceproof.cli import cmd_probe
    from faceproof.manifest import new_run_id

    run_id = new_run_id()
    run_dir = cfg.run_dir(run_id)
    code = cmd_probe(image, subject, run_id=run_id)

    res["run_id"] = run_id
    res["run_dir"] = run_dir.as_posix()
    probe = read_artifact(run_dir, "probe.json")
    res["probe"] = probe
    kept = retain_probe_image(run_dir, image)
    res["probe_image"] = kept.name if kept else None

    # exit codes come from Person 1's CLI: 0 accepted, others refuse
    if probe is None:
        job.step("consent", "fail", reason=f"stage1 exit {code}")
        job.step("stage1", "fail", reason="no probe.json was written")
        for s in ("stage2", "stage3", "anchor", "verify", "tamper"):
            job.step(s, "skipped")
        res["outcome"] = "ERROR"
        job.status = "error"
        job.error = f"Stage 1 produced no handoff (exit {code})"
        return

    consent = (probe or {}).get("consent") or {}
    if code != 0 and not consent:
        job.step("consent", "fail", reason="consent denied or absent")
    else:
        job.step("consent", "pass", scope=consent.get("scope"),
                 expires_at=consent.get("expires_at"),
                 subject_commitment=consent.get("subject_commitment"))

    if probe.get("status") == "rejected":
        job.step("stage1", "abstain", reason=probe.get("rejection_reason"),
                 quality=probe.get("quality"))
        stage2 = {"fusion_outcome": "ABSTAIN", "source": "stage1-reject"}
        write_abstain(run_dir, probe, stage2)
        for s in ("stage2", "stage3", "anchor", "verify", "tamper"):
            job.step(s, "skipped", reason="stage 1 rejected the probe")
        res["outcome"] = "ABSTAIN"
        res["abstain"] = read_artifact(run_dir, "abstain.json")
        job.emit("ABSTAIN - Stage 1 rejected this probe; no bundle was built.", "warn")
        return

    job.step("stage1", "pass", quality=probe.get("quality"),
             gate=probe.get("quality_gate"),
             embedding=probe.get("embedding"), model_id=probe.get("model_id"))

    # ---- Stage 2 (Person 2, via the bridge) ---------------------------- #
    job.step("stage2", "running")
    detail: Dict[str, Any] = {}
    if use_real_stage2:
        from faceproof.stage2_bridge import Stage2Unavailable, run_stage2

        try:
            payload = run_stage2(run_dir, detail=detail)
            job.emit(f"[stage 2] outcome={payload['fusion_outcome']} "
                     f"channels={payload['channels_used']}")
        except Stage2Unavailable as exc:
            job.emit(f"real Stage 2 unavailable: {exc}", "warn")

    try:
        stage2 = load_stage2(run_dir, allow_synthetic=allow_synthetic)
    except Stage2ResultMissing as exc:
        job.step("stage2", "fail", reason=str(exc))
        for s in ("stage3", "anchor", "verify", "tamper"):
            job.step(s, "skipped")
        res["outcome"] = "ERROR"
        job.status = "error"
        job.error = str(exc)
        return

    synthetic = stage2.get("source") == "synthetic-stub"
    res["stage2"] = stage2
    res["stage2_detail"] = detail
    res["synthetic"] = synthetic
    if synthetic:
        job.emit("--demo: Stage 2 result is the LABELLED SYNTHETIC fixture, "
                 "not a real search.", "warn")

    job.step(
        "stage2",
        "abstain" if stage2["fusion_outcome"] == "ABSTAIN" else "pass",
        outcome=stage2["fusion_outcome"],
        source=stage2.get("source"),
        synthetic=synthetic,
        channels_used=stage2.get("channels_used"),
        reason=stage2.get("reason"),
        channel_a=detail.get("channel_a"),
        channel_b=detail.get("channel_b"),
        snapshot_id=stage2.get("snapshot_id"),
    )

    # ---- Stage 3 (bundle) ---------------------------------------------- #
    job.step("stage3", "running")
    stage1 = load_record(run_dir)
    try:
        bundle, proofs = assemble_bundle(run_dir, stage1, stage2)
    except AbstainError as exc:
        write_abstain(run_dir, stage1, stage2)
        job.step("stage3", "abstain", reason=str(exc))
        for s in ("anchor", "verify", "tamper"):
            job.step(s, "skipped", reason="no bundle exists to anchor or verify")
        res["outcome"] = "ABSTAIN"
        res["abstain"] = read_artifact(run_dir, "abstain.json")
        job.emit(f"ABSTAIN: {exc}", "warn")
        return

    root = recompute_root(run_dir / "bundle.json")
    res["bundle"] = bundle
    res["proofs"] = proofs
    job.step("stage3", "pass", merkle_root=root,
             group_order=bundle.get("group_order"), n_groups=len(bundle.get("groups", {})))
    job.emit(f"[stage 3] bundle assembled - 8 groups, root={root}")

    # ---- anchor --------------------------------------------------------- #
    anchor_ok: Optional[bool] = None
    if do_anchor:
        job.step("anchor", "running")
        from faceproof.anchor import anchor as _anchor

        try:
            receipt = _anchor(run_dir)
            anchor_ok = True
            res["receipt"] = receipt
            job.step("anchor", "pass", **{k: receipt.get(k) for k in
                                          ("chain", "chain_id", "contract", "tx_hash",
                                           "block_number", "gas_used", "anchor_id",
                                           "explorer_url", "status")})
        except Exception as exc:
            anchor_ok = False
            job.step("anchor", "fail", reason=str(exc))
            job.emit(f"anchor FAILED: {exc}", "error")
    else:
        job.step("anchor", "skipped", reason="not requested")

    # ---- verify --------------------------------------------------------- #
    job.step("verify", "running")
    from faceproof.verify import tamper_demonstration, verify_run

    want_chain = bool(do_anchor and anchor_ok and check_chain)
    verified = verify_run(run_dir, check_chain=want_chain)
    try:
        res["verification"] = verification_rows(run_dir, check_chain=want_chain)
    except Exception as exc:                       # detail is best-effort only
        res["verification"] = {"rows": [], "chain_error": str(exc)}
    job.step("verify", "pass" if verified else "fail",
             verified=verified, chain_checked=want_chain,
             rows=res["verification"].get("rows"))

    # ---- tamper --------------------------------------------------------- #
    if do_tamper:
        job.step("tamper", "running")
        original_ok, detected = tamper_demonstration(run_dir)
        job.step("tamper", "pass" if detected else "fail",
                 original_passed=original_ok, tamper_detected=detected)
    else:
        job.step("tamper", "skipped", reason="not requested")

    res["outcome"] = "VERIFIED" if verified else "FAILED"
    if do_anchor and not anchor_ok:
        res["outcome"] = "FAILED"
