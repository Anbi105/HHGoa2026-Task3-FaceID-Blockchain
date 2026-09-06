"""The evidence bundle: exactly eight groups, one Merkle root (Stage 3, S7, S8).

The bundle is what a third party audits.  It must:

* contain **exactly** the eight groups below, in this order;
* carry only commitments, hashes and metadata - never a raw embedding, a
  raw image, a raw consent token, or raw post text;
* serialise deterministically (:func:`faceproof.canonical.canon`);
* commit to every group through a double-keccak Merkle leaf, so any single
  group can be disclosed and proven without revealing the other seven.

Group 0 (``probe``) and group 1 (``consent``) are taken *verbatim* from
Person 1's Stage 1 handoff (`probe.json`): the embedding commitment there
is already ``keccak256(salt || embedding_le_f32)`` with the salt from the
consent store, and the consent commitment is ``keccak256(consent_token)``.
Stage 3 re-uses those bytes; it never re-derives a commitment and never
generates a fresh salt.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from faceproof.canonical import _reject_floats, canon, q
from faceproof.config import cfg
from faceproof.merkle import build, hexstr, leaf, proof, root

# Canonical order.  Index is meaningful: match_location is group 2 and that
# is the group the selective-disclosure demo reveals.
GROUPS: Tuple[str, ...] = (
    "probe",            # 0
    "consent",          # 1
    "match_location",   # 2
    "match_author",     # 3
    "match_text",       # 4
    "match_image",      # 5
    "scores",           # 6
    "provenance",       # 7
)

BUNDLE_FILENAME = "bundle.json"
PROOFS_FILENAME = "proofs.json"
ABSTAIN_FILENAME = "abstain.json"


class AbstainError(ValueError):
    """Raised when a bundle is requested for a run Stage 2 did not accept.

    Stage 3 records the abstain (see :func:`write_abstain`) and stops.  It
    does not manufacture a positive attestation.
    """


def sha256_hex(text: str) -> str:
    """Opaque SHA-256 of UTF-8 text - used for post text, never the text itself."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_z() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# Group builders - each returns a flat dict of strings / ints only
# ---------------------------------------------------------------------------


def make_probe_group(commitment: str, model_id: str, det_score: Any, blur_var: Any) -> Dict[str, Any]:
    """0 - probe - salted commitment to the embedding, plus quality context.

    ``commitment`` is Person 1's ``keccak256(salt || embedding)``; the raw
    embedding stays in ``embedding.f32`` on the host and is never referenced.
    """
    return {
        "commitment": str(commitment),
        "model_id": str(model_id),
        "det_score": det_score if isinstance(det_score, str) else q(det_score),
        "blur_var": blur_var if isinstance(blur_var, str) else q(blur_var),
    }


def make_consent_group(subject_ref: str, consent_commitment: str, granted_at: str, scope: str) -> Dict[str, Any]:
    """1 - consent - commitment to the consent token, grant time, scope.

    ``subject_ref`` is an opaque local reference (Person 1 exposes only the
    subject commitment); no subject id, no PII.
    """
    return {
        "subject_ref": str(subject_ref),
        "commitment": str(consent_commitment),
        "granted_at": str(granted_at),
        "scope": str(scope),
    }


def make_match_location_group(platform: str, post_url: str, at_uri: str) -> Dict[str, Any]:
    """2 - match_location - platform, canonical post URL, AT-URI."""
    return {
        "platform": str(platform),
        "post_url": str(post_url),
        "at_uri": str(at_uri),
    }


def make_match_author_group(author_did: str, handle: str) -> Dict[str, Any]:
    """3 - match_author - author DID and the handle seen at retrieval."""
    return {
        "author_did": str(author_did),
        "handle": str(handle),
    }


def make_match_text_group(text_sha256: str, text_length: int) -> Dict[str, Any]:
    """4 - match_text - SHA-256 of the post text and its length. No raw text."""
    return {
        "sha256": str(text_sha256),
        "length": int(text_length),
    }


def make_match_image_group(image_sha256: str, phash: str, source_url: str) -> Dict[str, Any]:
    """5 - match_image - image SHA-256, perceptual hash, source URL."""
    return {
        "sha256": str(image_sha256),
        "phash": str(phash),
        "source_url": str(source_url),
    }


def make_scores_group(cosine: Any, margin: Any, threshold: Any, fusion_verdict: str) -> Dict[str, Any]:
    """6 - scores - cosine, margin, threshold (fixed-precision), fusion verdict."""
    return {
        "cosine": cosine if isinstance(cosine, str) else q(cosine),
        "margin": margin if isinstance(margin, str) else q(margin),
        "threshold": threshold if isinstance(threshold, str) else q(threshold),
        "fusion_verdict": str(fusion_verdict),
    }


def make_provenance_group(
    pipeline_version: str,
    schema_id: str,
    index_snapshot_id: str,
    retrieval_timestamp: str,
    channels_used: List[str],
) -> Dict[str, Any]:
    """7 - provenance - pipeline / schema / snapshot ids, retrieval time, channels."""
    return {
        "pipeline_version": str(pipeline_version),
        "schema_id": str(schema_id),
        "index_snapshot_id": str(index_snapshot_id),
        "retrieval_timestamp": str(retrieval_timestamp),
        "channels_used": [str(c) for c in channels_used],
    }


# ---------------------------------------------------------------------------
# Tree over the groups
# ---------------------------------------------------------------------------


def _ordered_payloads(groups: Dict[str, Dict[str, Any]]) -> List[bytes]:
    missing = [g for g in GROUPS if g not in groups]
    extra = [g for g in groups if g not in GROUPS]
    if missing or extra:
        raise ValueError(
            f"bundle must contain exactly the 8 groups {GROUPS}; "
            f"missing={missing} extra={extra}"
        )
    _reject_floats(groups)
    return [canon(groups[name]) for name in GROUPS]


def canonical_leaves(groups: Dict[str, Dict[str, Any]]) -> List[bytes]:
    """The eight leaf hashes, ``leaf(canon(group))``, in canonical order."""
    return [leaf(p) for p in _ordered_payloads(groups)]


def compute_root(groups: Dict[str, Dict[str, Any]]) -> str:
    """Merkle root of the eight groups as ``0x``-hex."""
    return hexstr(root(build(canonical_leaves(groups))))


def build_bundle(groups: Dict[str, Dict[str, Any]], *, schema_id: Optional[str] = None) -> Dict[str, Any]:
    """Assemble the bundle dict (groups + root + metadata) from eight groups.

    The bundle is a pure function of its groups - no wall-clock field - so
    two hosts given the same Stage 1 / Stage 2 inputs write byte-identical
    ``bundle.json``.  Timing lives in ``manifest.jsonl`` / ``receipt.json``.
    """
    return {
        "schema_id": schema_id or cfg.schema_id,
        "pipeline_version": cfg.pipeline_version,
        "group_order": list(GROUPS),
        "merkle_root": compute_root(groups),
        "groups": {name: groups[name] for name in GROUPS},
    }


def build_proofs(groups: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Per-group audit paths for selective disclosure."""
    leaves = canonical_leaves(groups)
    layers = build(leaves)
    return {
        "merkle_root": hexstr(root(layers)),
        "group_order": list(GROUPS),
        "groups": {
            name: {
                "index": i,
                "leaf": hexstr(leaves[i]),
                "proof": [hexstr(p) for p in proof(layers, i)],
            }
            for i, name in enumerate(GROUPS)
        },
    }


def recompute_root(bundle: Any) -> str:
    """Derive the root from ``bundle['groups']`` alone, ignoring any stored root.

    Accepts a bundle dict or a path to ``bundle.json``.  This is what
    verification uses - it must never trust ``bundle['merkle_root']``.
    """
    if isinstance(bundle, (str, Path)):
        bundle = json.loads(Path(bundle).read_text(encoding="utf-8"))
    return compute_root(bundle["groups"])


# ---------------------------------------------------------------------------
# Privacy guard
# ---------------------------------------------------------------------------

_FORBIDDEN_KEYS = {"embedding", "embeddings", "vector", "consent_token", "token", "text", "raw_text"}


def verify_bundle_privacy(bundle: Dict[str, Any]) -> None:
    """Fail if anything that must stay local leaked into the bundle."""
    groups = bundle.get("groups", {})
    for gname, gval in groups.items():
        for key in gval:
            if key in _FORBIDDEN_KEYS:
                raise ValueError(f"forbidden key {key!r} in group {gname!r}")
        # a 512-float list is the classic accident
        for key, val in gval.items():
            if isinstance(val, list) and len(val) >= 64 and all(
                isinstance(x, (int, float)) for x in val
            ):
                raise ValueError(f"group {gname!r} field {key!r} looks like a raw vector")

    probe = groups.get("probe", {})
    c = probe.get("commitment", "")
    if not (isinstance(c, str) and c.startswith("0x") and len(c) == 66):
        raise ValueError("probe.commitment must be a 0x-prefixed 32-byte hex commitment")
    # canon() would already reject a raw float anywhere in the bundle
    _reject_floats(bundle)


# ---------------------------------------------------------------------------
# Assembly from real Stage 1 + Stage 2 output
# ---------------------------------------------------------------------------


def assemble_groups(stage1_record: Dict[str, Any], stage2: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build the eight groups from Person 1's handoff and a normalised Stage 2 result.

    ``stage2`` is the shape returned by
    :func:`faceproof.stage2_adapter.load_stage2`.  Raises :class:`AbstainError`
    if Stage 2 did not produce a match.
    """
    outcome = str(stage2.get("fusion_outcome", "ABSTAIN")).upper()
    match = stage2.get("match")
    if outcome == "ABSTAIN" or not match:
        raise AbstainError(
            f"Stage 2 outcome is {outcome!r} - refusing to assemble an evidence bundle"
        )

    quality = stage1_record.get("quality", {})
    emb = stage1_record.get("embedding", {})
    consent = stage1_record.get("consent", {})

    commitment = emb.get("commitment")
    if not commitment:
        raise ValueError("Stage 1 record has no embedding commitment (rejected probe?)")

    subject_commitment = consent.get("subject_commitment", "")

    groups: Dict[str, Dict[str, Any]] = {
        "probe": make_probe_group(
            commitment=commitment,
            model_id=stage1_record.get("model_id", cfg.model_id),
            det_score=quality.get("det_score") or q(0),
            blur_var=quality.get("blur_var") or q(0),
        ),
        "consent": make_consent_group(
            subject_ref=subject_commitment,
            consent_commitment=subject_commitment,
            granted_at=consent.get("granted_at", ""),
            scope=consent.get("scope", cfg.consent_scope),
        ),
        "match_location": make_match_location_group(
            platform=match["platform"],
            post_url=match["post_url"],
            at_uri=match["post_uri"],
        ),
        "match_author": make_match_author_group(
            author_did=match["author_did"],
            handle=match["author_handle"],
        ),
        "match_text": make_match_text_group(
            text_sha256=match["text_sha256"],
            text_length=match["text_length"],
        ),
        "match_image": make_match_image_group(
            image_sha256=match["image_sha256"],
            phash=match["phash"],
            source_url=match["source_url"],
        ),
        "scores": make_scores_group(
            cosine=match["cosine"],
            margin=match["margin"],
            threshold=match["threshold"],
            fusion_verdict=outcome,
        ),
        "provenance": make_provenance_group(
            pipeline_version=stage2.get("pipeline_version", cfg.pipeline_version),
            schema_id=cfg.schema_id,
            index_snapshot_id=stage2.get("snapshot_id", ""),
            retrieval_timestamp=stage2.get("retrieval_timestamp", _now_z()),
            channels_used=stage2.get("channels_used", ["channel_a"]),
        ),
    }
    return groups


def assemble_bundle(
    run_dir: Path | str,
    stage1_record: Dict[str, Any],
    stage2: Dict[str, Any],
    *,
    write: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Build groups -> bundle + proofs, optionally writing ``bundle.json`` / ``proofs.json``.

    ``bundle.json`` is written as canonical bytes so its on-disk form is
    itself reproducible.
    """
    groups = assemble_groups(stage1_record, stage2)
    bundle = build_bundle(groups)
    verify_bundle_privacy(bundle)
    proofs = build_proofs(groups)

    if write:
        run_path = Path(run_dir)
        run_path.mkdir(parents=True, exist_ok=True)
        (run_path / BUNDLE_FILENAME).write_bytes(canon(bundle))
        (run_path / PROOFS_FILENAME).write_bytes(canon(proofs))

    return bundle, proofs


def write_abstain(run_dir: Path | str, stage1_record: Dict[str, Any], stage2: Dict[str, Any]) -> Dict[str, Any]:
    """Record an honest non-attestation for an abstaining run (S abstain path)."""
    record = {
        "schema_id": "faceproof.abstain.v1",
        "pipeline_version": cfg.pipeline_version,
        "created_at": _now_z(),
        "status": "ABSTAIN",
        "fusion_outcome": str(stage2.get("fusion_outcome", "ABSTAIN")).upper(),
        "stage2_source": stage2.get("source", "unknown"),
        "probe_status": stage1_record.get("status", "unknown"),
        "note": "Stage 2 produced no accepted match. No Merkle root, no anchor.",
    }
    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)
    (run_path / ABSTAIN_FILENAME).write_bytes(canon(record))
    return record
