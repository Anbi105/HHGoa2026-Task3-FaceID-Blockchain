"""Stage 3's read-only adapter onto Stage 2's discovery / fusion output (S6, S24).

Person 2 owns Stage 2 (branch ``origin/person2``).  Stage 3 must:

* not depend on that branch being merged,
* consume Stage 2's *documented interface* rather than reach into its code,
* never fabricate a match when Stage 2 abstains.

This module is the single seam.  :func:`load_stage2` reads a Stage 2 result
file if one was written into the run directory; otherwise it returns a
clearly labelled synthetic fixture so the Stage 3 pipeline is demonstrable
on its own.  Channel B stays disabled by design - no probe image ever
leaves the host.

Nothing here is Person 2's implementation; it is the smallest possible
consumer of their interface, and it normalises everything so
:func:`faceproof.bundle.assemble_bundle` sees one shape.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from faceproof.canonical import q
from faceproof.config import cfg

# The four verdicts Stage 2 fusion can return.  ABSTAIN is a first-class
# result: Stage 3 records it and stops, it does not anchor.
OUTCOMES = ("CORROBORATED", "SINGLE_CHANNEL_A", "SINGLE_CHANNEL_B", "ABSTAIN")

# Filenames Person 2's stage may drop into out/run-<id>/.  First hit wins.
_STAGE2_FILENAMES = ("stage2.json", "discovery.json", "match.json", "fuse.json")


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_z() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _first_present(d: Dict[str, Any], *keys: str, default: Any = "") -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def normalize(raw: Dict[str, Any], *, source: str) -> Dict[str, Any]:
    """Map a raw Stage 2 record onto the shape Stage 3 consumes.

    Accepts the loose interface described in the task brief (``score``,
    ``post_url``, ``post_uri``, ``author_did`` ...), a nested ``hits[0]`` /
    ``match`` / ``winner`` object, or a flat dict.  Raw post text is hashed
    and discarded here so it can never travel further.
    """
    outcome = str(
        _first_present(raw, "fusion_outcome", "outcome", "fusion", default="ABSTAIN")
    ).upper()
    if outcome not in OUTCOMES:
        outcome = "ABSTAIN"

    hit: Dict[str, Any] = {}
    for key in ("match", "winner", "top"):
        if isinstance(raw.get(key), dict):
            hit = dict(raw[key])
            break
    else:
        hits = raw.get("hits")
        if isinstance(hits, list) and hits and isinstance(hits[0], dict):
            hit = dict(hits[0])
        else:
            hit = raw  # flat record

    channels = raw.get("channels_used") or raw.get("channels")
    if not channels:
        channels = ["channel_a"] if outcome != "SINGLE_CHANNEL_B" else ["channel_b"]
        if outcome == "CORROBORATED":
            channels = ["channel_a", "channel_b"]
    channels = [str(c) for c in channels]

    result: Dict[str, Any] = {
        "source": source,
        "fusion_outcome": outcome,
        "channels_used": channels,
        "snapshot_id": str(
            _first_present(raw, "snapshot_id", "index_snapshot_id", default="")
            or (raw.get("snapshot") or {}).get("snapshot_id", "")
        ),
        "retrieval_timestamp": str(
            # NB: never fall back to ``accept_at`` here - in this codebase that
            # key is a cosine score threshold (~0.55), not a time.
            _first_present(raw, "retrieval_timestamp", "retrieved_at", "retrievedAt",
                           default=_now_z())
        ),
        "pipeline_version": str(
            _first_present(raw, "pipeline_version", default=cfg.pipeline_version)
        ),
        "match": None,
    }

    if outcome == "ABSTAIN":
        return result

    raw_text = hit.get("text")
    text_sha = _first_present(hit, "text_sha256", "text_hash")
    if not text_sha and isinstance(raw_text, str):
        text_sha = _sha256_hex(raw_text)
    text_len = hit.get("text_len", hit.get("text_length"))
    if text_len in (None, "") and isinstance(raw_text, str):
        text_len = len(raw_text)

    result["match"] = {
        "platform": str(_first_present(hit, "platform", default="bluesky")),
        "post_url": str(_first_present(hit, "post_url", "url", "canonical_post_url")),
        "post_uri": str(_first_present(hit, "post_uri", "at_uri", "atproto_uri")),
        "author_did": str(_first_present(hit, "author_did", "did")),
        "author_handle": str(_first_present(hit, "author_handle", "handle")),
        "text_sha256": str(text_sha or _sha256_hex("")),
        "text_length": int(text_len or 0),
        "image_sha256": str(_first_present(hit, "image_sha256", "image_hash")),
        "phash": str(_first_present(hit, "phash", "perceptual_hash")),
        "source_url": str(
            _first_present(hit, "source_url", "image_url")
            or _first_present(hit, "post_url", "url")
        ),
        "cosine": q(_first_present(hit, "score", "cosine", "cosine_similarity", default=0)),
        "margin": q(_first_present(raw, "margin", default=hit.get("margin", 0))),
        "threshold": q(_first_present(raw, "threshold", "accept_threshold",
                                      default=cfg.accept_at)),
    }
    return result


def _synthetic() -> Dict[str, Any]:
    """A labelled stand-in so Stage 3 runs without Person 2's branch.

    It is deliberately obvious in the manifest and the bundle provenance
    (``source: synthetic-stub``) that no real discovery took place.
    """
    raw = {
        "fusion_outcome": "SINGLE_CHANNEL_A",
        "channels_used": ["channel_a:synthetic-stub"],
        "snapshot_id": "synthetic-snapshot-000",
        # fixed, not wall-clock: the stub must produce a reproducible root
        "retrieval_timestamp": "2026-01-01T00:00:00Z",
        "margin": cfg.min_margin + 0.05,
        "threshold": cfg.accept_at,
        "match": {
            "platform": "bluesky",
            "post_url": "https://bsky.app/profile/demo.faceproof.test/post/3ksyntheticdemo",
            "post_uri": "at://did:plc:faceproofdemo0000/app.bsky.feed.post/3ksyntheticdemo",
            "author_did": "did:plc:faceproofdemo0000",
            "author_handle": "demo.faceproof.test",
            "text": "Synthetic Stage-2 fixture - no real post was retrieved.",
            "image_sha256": hashlib.sha256(b"synthetic-image").hexdigest(),
            "phash": "d8e0f0f0d8e0f0f0",
            "score": cfg.accept_at + 0.15,
        },
    }
    return normalize(raw, source="synthetic-stub")


def load_stage2(run_dir: Path | str, embedding: Optional[Any] = None) -> Dict[str, Any]:
    """Return the normalised Stage 2 result for ``run_dir``.

    Order of preference:

    1. a Stage 2 file already present in the run directory (Person 2's
       output, consumed as-is);
    2. a synthetic fixture, clearly labelled, so Stage 3 is self-contained.

    ``embedding`` is accepted for signature compatibility with a real
    discovery call but is intentionally unused - Stage 3 never re-runs
    matching.
    """
    run_path = Path(run_dir)
    for name in _STAGE2_FILENAMES:
        candidate = run_path / name
        if candidate.exists():
            raw = json.loads(candidate.read_text(encoding="utf-8"))
            return normalize(raw, source=f"person2-file:{name}")
    return _synthetic()
