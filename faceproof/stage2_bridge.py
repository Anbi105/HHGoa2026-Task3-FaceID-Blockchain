"""Stage 2 bridge - run Person 2's real discovery and emit Stage 3's input (S6).

Person 2 owns Stage 2 (branch ``person2``).  Their code is a complete parallel
pipeline whose package is *also* called ``faceproof`` with the same module
names as Stage 1/3 but an older, incompatible implementation, so it cannot be
imported normally alongside this package.

This module is the smallest possible seam.  It:

* loads Person 2's ``fuse.py``, ``channel_b.py`` and ``index.py`` from
  ``vendor/stage2/`` by file path (never modifying them, never putting them
  on ``sys.path``);
* reads the Stage 1 handoff embedding (``embedding.f32``);
* runs Channel A = Person 2's ``index.search`` **iff** a local FAISS index is
  present under ``data/index/`` - it never fabricates a corpus;
* runs Channel B = Person 2's ``channel_b.discover``;
* fuses the two with Person 2's ``fuse.fuse``;
* writes ``out/run-<id>/stage2.json`` in the shape
  :func:`faceproof.stage2_adapter.normalize` already consumes.

Raw post text is hashed here and never written to disk.  With no local index,
Person 2's ``fuse`` returns ``ABSTAIN`` and Stage 3 honestly records the
abstain - there is no synthetic match on this path.

What the vendored tree actually contains
----------------------------------------
Be precise about this, because "runs Person 2's real modules" oversells it:

* ``fuse.fuse`` is complete - the three-outcome corroboration rule, used as-is.
* ``channel_b.discover`` is a **three-line stub** that always returns
  ``{"accepted": False, "reason": "no_SERPAPI_KEY_or_ephemeral_host"}``.
  Reverse-image search is not implemented on the ``person2`` branch, so
  ``SINGLE_CHANNEL_B`` is unreachable through this bridge today.
* ``index.search`` is complete and is genuine FAISS retrieval - but
  ``index.build`` is **not reachable** here: it does ``from .face import
  probe_image``, a relative import that cannot resolve under
  :func:`_load_by_path`.  Building a corpus therefore still runs on Person 2's
  own tree, not through this seam.  See ``data/index/README.md``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import time
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional

from faceproof.config import cfg
from faceproof.handoff import load_record, read_embedding
from faceproof.manifest import Manifest

STAGE2_FILENAME = "stage2.json"
STAGE2_SCHEMA_ID = "faceproof.stage2.bridge.v1"

# Where Person 2's package may live, relative to the repo root.  The vendored
# copy is tried first; the side-by-side reference clone is the fallback (that
# clone keeps the original ``person2`` branch layout, so its path is longer).
_P2_PKG_CANDIDATES = (
    "vendor/stage2/faceproof",
    "person2/files-mentioned-by-the-user-hhgoa/faceproof/faceproof",
)

_REPO_ROOT = Path(__file__).resolve().parent.parent


class Stage2Unavailable(RuntimeError):
    """Person 2's Stage 2 modules could not be located on disk."""


# ---------------------------------------------------------------------------
# Load Person 2's real modules by path (no import-system pollution)
# ---------------------------------------------------------------------------


def _p2_pkg_dir() -> Path:
    for rel in _P2_PKG_CANDIDATES:
        cand = _REPO_ROOT / rel
        if (cand / "fuse.py").exists():
            return cand
    raise Stage2Unavailable(
        "Person 2's Stage 2 package was not found. Expected one of: "
        + ", ".join(_P2_PKG_CANDIDATES)
    )


def _load_by_path(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_p2_{name}", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise Stage2Unavailable(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_person2_modules() -> Dict[str, ModuleType]:
    """Return Person 2's ``{fuse, channel_b, index}`` modules, loaded by path.

    ``channel_a.py`` is intentionally not loaded: it is a thin wrapper around
    ``index.search`` whose ``from .index import`` line cannot resolve outside a
    package.  This bridge calls ``index.search`` directly and reproduces the
    same top-hit field surfacing.
    """
    pkg = _p2_pkg_dir()
    return {
        "fuse": _load_by_path("fuse", pkg / "fuse.py"),
        "channel_b": _load_by_path("channel_b", pkg / "channel_b.py"),
        "index": _load_by_path("index", pkg / "index.py"),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_z() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _index_dir() -> Path:
    return cfg.data_dir / "index"


def _index_present() -> bool:
    d = _index_dir()
    return all((d / f).exists() for f in ("faiss.bin", "sidecar.jsonl", "snapshot.json"))


def _faiss_available() -> bool:
    """Is Person 2's vector backend importable?

    Split out so a unit test of the bridge's own control flow does not have to
    install a 30 MB native library to exercise the paths past this check.
    """
    try:
        import faiss  # noqa: F401  (Person 2's index.search imports it too)
    except ImportError:
        return False
    return True


def index_stats() -> Optional[Dict[str, Any]]:
    """Person 2's ``data/index/snapshot.json`` if a local index exists."""
    snap = _index_dir() / "snapshot.json"
    if not snap.exists():
        return None
    try:
        return json.loads(snap.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # pragma: no cover - defensive
        return None


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------


def _run_channel_a(index_mod: ModuleType, embedding, *, log) -> Dict[str, Any]:
    """Channel A = Person 2's ``index.search`` against a *real* local index.

    Returns Person 2's own result dict (``accepted``/``reason``/``hits``/
    ``margin``/``snapshot``), plus the three top-hit keys that Person 2's
    ``channel_a.discover`` surfaces (``post_uri``/``post_url``/``image_sha256``).
    If no local index is present, returns a not-accepted result and does not
    fabricate hits.
    """
    if not _index_present():
        log("STAGE 2", "channel_a", status="no_local_index", dir=str(_index_dir()))
        return {
            "accepted": False,
            "reason": "no_local_index",
            "hits": [],
            "margin": 0.0,
            "snapshot": {},
        }

    if not _faiss_available():
        log("STAGE 2", "channel_a", status="faiss_not_installed")
        return {
            "accepted": False,
            "reason": "faiss_not_installed",
            "hits": [],
            "margin": 0.0,
            "snapshot": {},
        }

    try:
        result = index_mod.search(embedding, cfg, out_dir=str(_index_dir()))
    except Exception as exc:  # a partial/corrupt index must not kill the take
        log("STAGE 2", "channel_a", status="index_error", error=str(exc)[:120])
        return {
            "accepted": False,
            "reason": "index_error",
            "hits": [],
            "margin": 0.0,
            "snapshot": {},
        }
    hits = result.get("hits") or []
    if hits:  # mirror channel_a.discover's top-hit surfacing
        for k in ("post_uri", "post_url", "image_sha256"):
            result.setdefault(k, hits[0].get(k))
    snap = result.get("snapshot") or {}
    log(
        "STAGE 2",
        "channel_a",
        status=result.get("reason"),
        accepted=result.get("accepted"),
        n_hits=len(hits),
        margin=round(float(result.get("margin", 0.0)), 6),
        snapshot_id=snap.get("snapshot_id", ""),
    )
    return result


def _run_channel_b(channel_b_mod: ModuleType, embedding, *, log) -> Dict[str, Any]:
    """Channel B = Person 2's ``channel_b.discover`` (unchanged)."""
    result = channel_b_mod.discover(embedding, cfg)
    log(
        "STAGE 2",
        "channel_b",
        accepted=result.get("accepted"),
        reason=result.get("reason"),
    )
    return result


# ---------------------------------------------------------------------------
# Bridge entry point
# ---------------------------------------------------------------------------


def _match_from_hit(hit: Dict[str, Any]) -> Dict[str, Any]:
    """Build the ``match`` block for stage2.json from a Person 2 index hit.

    Only fields Person 2 actually produces are passed through.  ``text`` is
    hashed here and dropped; ``image_sha256`` / ``phash`` are left empty when
    Person 2's corpus does not carry them (it computes no perceptual hash).
    """
    raw_text = hit.get("text")
    text_sha = hit.get("text_sha256") or (
        _sha256_hex(raw_text) if isinstance(raw_text, str) else _sha256_hex("")
    )
    text_len = hit.get("text_length")
    if text_len in (None, "") and isinstance(raw_text, str):
        text_len = len(raw_text)
    return {
        "platform": str(hit.get("platform", "bluesky")),
        "post_url": str(hit.get("post_url", "")),
        "post_uri": str(hit.get("post_uri", "")),
        "author_did": str(hit.get("author_did", "")),
        "author_handle": str(hit.get("author_handle", "")),
        "text_sha256": str(text_sha),
        "text_length": int(text_len or 0),
        "image_sha256": str(hit.get("image_sha256", "") or ""),
        "phash": str(hit.get("phash", "") or ""),
        "source_url": str(hit.get("image_url") or hit.get("post_url", "")),
        "score": float(hit.get("score", 0.0)),
    }


def run_stage2(run_dir: Path | str, *, write: bool = True) -> Dict[str, Any]:
    """Run Person 2's Stage 2 for ``run_dir`` and (optionally) write stage2.json.

    Returns the payload dict.  Raises :class:`Stage2Unavailable` only if Person
    2's package cannot be found on disk.
    """
    run_path = Path(run_dir)
    manifest = Manifest(run_path)

    def log(*a: Any, **k: Any) -> None:
        try:
            manifest.log(*a, **k)
        except Exception:  # pragma: no cover - logging must never break the run
            pass

    stage1 = load_record(run_path)
    p2 = load_person2_modules()

    if stage1.get("status") == "rejected":
        payload = _abstain_payload(reason="stage1_rejected",
                                   channels=["channel_a:skipped", "channel_b:skipped"])
        if write:
            _write(run_path, payload)
        log("STAGE 2", "bridge", outcome="ABSTAIN", reason="stage1_rejected")
        return payload

    embedding = read_embedding(run_path)

    channel_a = _run_channel_a(p2["index"], embedding, log=log)
    channel_b = _run_channel_b(p2["channel_b"], embedding, log=log)

    fused = p2["fuse"].fuse(channel_a, channel_b)
    outcome = str(fused.get("outcome", "ABSTAIN")).upper()
    log("STAGE 2", "fusion", outcome=outcome)

    snap = channel_a.get("snapshot") or {}
    channels_used = _channels_used(outcome, channel_a, channel_b)

    if outcome == "ABSTAIN":
        payload = _abstain_payload(
            reason=channel_a.get("reason") or "fusion_abstain",
            channels=channels_used,
            snapshot_id=snap.get("snapshot_id", ""),
        )
        if write:
            _write(run_path, payload)
        return payload

    # The winning record must come from the channel that actually won - not
    # channel A's (possibly empty) hits regardless of outcome.  If the winning
    # channel produced no locatable record, refuse to emit a positive match
    # with an empty body: downgrade to ABSTAIN.
    winner = _winner_for(outcome, channel_a, channel_b)
    if not (winner.get("post_url") or winner.get("post_uri")):
        payload = _abstain_payload(
            reason=f"{outcome.lower()}_without_locatable_match",
            channels=channels_used,
            snapshot_id=snap.get("snapshot_id", ""),
        )
        if write:
            _write(run_path, payload)
        log("STAGE 2", "bridge", outcome="ABSTAIN", reason=payload["reason"])
        return payload

    payload: Dict[str, Any] = {
        "schema_id": STAGE2_SCHEMA_ID,
        "source": "person2-bridge",
        "fusion_outcome": outcome,
        "channels_used": channels_used,
        "pipeline_version": "faceproof/1.0.0",  # Person 2's config pipeline_version
        "snapshot_id": str(snap.get("snapshot_id", "")),
        "retrieval_timestamp": _now_z(),
        "margin": float(channel_a.get("margin", 0.0)),
        "threshold": float(cfg.accept_at),
        "match": _match_from_hit(winner),
    }
    if write:
        _write(run_path, payload)
    return payload


def _winner_for(outcome: str, a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """The match record from whichever channel the fusion outcome credits.

    ``SINGLE_CHANNEL_B`` takes channel B's record (Person 2's ``fuse`` also
    nests it under ``"b"``); everything else takes channel A's top hit.
    """
    if outcome == "SINGLE_CHANNEL_B":
        for cand in (b, b.get("b") if isinstance(b, dict) else None,
                     b.get("match") if isinstance(b, dict) else None):
            if isinstance(cand, dict) and (cand.get("post_url") or cand.get("post_uri")):
                return cand
        return {}
    return (a.get("hits") or [{}])[0]


def _channels_used(outcome: str, a: Dict[str, Any], b: Dict[str, Any]) -> List[str]:
    if outcome == "CORROBORATED":
        return ["channel_a", "channel_b"]
    if outcome == "SINGLE_CHANNEL_A":
        return ["channel_a"]
    if outcome == "SINGLE_CHANNEL_B":
        return ["channel_b"]
    # abstain: record what was attempted / why each channel dropped out
    return [
        f"channel_a:{a.get('reason', 'n/a')}",
        f"channel_b:{b.get('reason', 'n/a')}",
    ]


def _abstain_payload(*, reason: str, channels: List[str],
                     snapshot_id: str = "") -> Dict[str, Any]:
    return {
        "schema_id": STAGE2_SCHEMA_ID,
        "source": "person2-bridge",
        "fusion_outcome": "ABSTAIN",
        "channels_used": channels,
        "pipeline_version": "faceproof/1.0.0",
        "snapshot_id": snapshot_id,
        "retrieval_timestamp": _now_z(),
        "reason": reason,
        "match": None,
    }


def _write(run_path: Path, payload: Dict[str, Any]) -> Path:
    run_path.mkdir(parents=True, exist_ok=True)
    path = run_path / STAGE2_FILENAME
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
