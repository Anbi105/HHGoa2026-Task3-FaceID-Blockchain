"""The Stage 1 → Stage 2 boundary artifact (§2).

The serialised artifact between stages is not decoration: it is what lets
each stage run on its own, lets a run resume after a failure mid-recording,
and proves to a judge that Stage 3 could not have influenced Stage 2.

Every run writes, under ``out/run-<id>/``:

    probe.json      the record below — no raw biometrics, safe to show
    embedding.f32   the 512-d vector, little-endian float32 (LOCAL ONLY)
    manifest.jsonl  the append-only run log

Numbers in ``probe.json`` are pre-formatted as fixed-precision strings
(D9).  Re-verification has to reproduce bytes exactly, and float repr
differences across machines silently break every proof — so no bare float
ever reaches the record.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from faceproof.config import cfg
from faceproof.consent import (
    ConsentRecord,
    embedding_bytes,
    embedding_commitment,
    subject_commitment,
)
from faceproof.face import Probe, Rejection
from faceproof.manifest import sha256_bytes, sha256_file

EMBEDDING_FILENAME = "embedding.f32"
PROBE_FILENAME = "probe.json"


def q(x: float, precision: Optional[int] = None) -> str:
    """Quantise a number to a fixed-precision decimal *string* (D9).

    Every number that reaches a serialised record goes through here.  This
    is the single reason two machines produce the same bytes.
    """
    p = cfg.float_precision if precision is None else precision
    return f"{float(x):.{p}f}"


def _reject_floats(obj: Any, path: str = "$") -> None:
    """Fail loudly if a bare float survived into the record.

    Do not weaken this.  A float in the bundle is the single most common
    cause of "verification passes locally, fails against chain" (§14).
    """
    if isinstance(obj, float):
        raise TypeError(f"raw float at {path} — every number must go through q()")
    if isinstance(obj, dict):
        for k, v in obj.items():
            _reject_floats(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _reject_floats(v, f"{path}[{i}]")


def build_record(
    run_id: str,
    image_path: Path | str,
    consent: ConsentRecord,
    probe: Optional[Probe] = None,
    rejection: Optional[Rejection] = None,
    embedding_digest: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble the Stage 2 handoff record.

    Exactly one of *probe* / *rejection* is expected.  A rejected probe
    still produces a record — an abstain is a first-class result, and the
    rejection evidence is exactly what makes the recording convincing.
    """
    image_path = Path(image_path)
    accepted = probe is not None

    commitment_hex: Optional[str] = None
    if accepted:
        salt = consent.salt
        if salt is None:
            raise ValueError(
                "consent salt has been erased — cannot commit to this embedding"
            )
        commitment, _ = embedding_commitment(probe.embedding, salt=salt)
        commitment_hex = "0x" + commitment.hex()

    quality: Dict[str, Any]
    if accepted:
        quality = {
            "det_score": q(probe.det_score),
            "face_px": int(probe.face_px),
            "blur_var": q(probe.blur_var),
            "n_faces": probe.n_faces,
            "secondary_ratio": q(probe.secondary_ratio),
            "bbox": [q(v, 2) for v in probe.bbox],
        }
    else:
        m = dict(rejection.metrics) if rejection is not None else {}
        quality = {
            "det_score": q(m["det_score"]) if "det_score" in m else None,
            "face_px": int(m["face_px"]) if "face_px" in m else None,
            "blur_var": q(m["blur_var"]) if "blur_var" in m else None,
            "n_faces": m.get("n_faces"),
            "secondary_ratio": q(m["secondary_ratio"]) if "secondary_ratio" in m else None,
            "bbox": None,
        }

    gate = {
        "min_det_score": q(cfg.min_det_score),
        "min_face_px": cfg.min_face_px,
        "min_blur_var": q(cfg.min_blur_var),
        "max_secondary_face_ratio": q(cfg.max_secondary_face_ratio),
    }

    record: Dict[str, Any] = {
        "schema_id": cfg.probe_schema_id,
        "run_id": run_id,
        "status": "accepted" if accepted else "rejected",
        "rejection_reason": None if accepted else str(rejection),
        "pipeline_version": cfg.pipeline_version,
        "model_id": cfg.model_id,
        "image": {
            "filename": image_path.name,
            "sha256": sha256_file(image_path) if image_path.exists() else None,
        },
        "quality": quality,
        "quality_gate": gate,
        # Consent leaves — opaque digests only, no subject_id, no PII.
        "consent": consent.public(),
        "embedding": {
            "dim": 512,
            "dtype": "float32",
            "byte_order": "little",
            "l2_normalised": True,
            # keccak256(salt || embedding) — the Merkle leaf for Stage 3.
            "commitment": commitment_hex,
            # sha256 of the local vector file, so Stage 2 can prove it read
            # the same bytes Stage 1 wrote.  Not a biometric.
            "sha256": embedding_digest,
            "file": EMBEDDING_FILENAME if accepted else None,
        },
        "config": {
            k: (q(v) if isinstance(v, float) else v) for k, v in cfg.public().items()
        },
    }

    _reject_floats(record)
    return record


def write_embedding(run_dir: Path | str, embedding: np.ndarray) -> tuple[Path, str]:
    """Write the raw vector locally and return ``(path, sha256)``.

    LOCAL ONLY.  This file is the one genuinely biometric artifact in the
    run directory; ``out/`` is gitignored and it never reaches the chain.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    data = embedding_bytes(embedding)
    path = run_dir / EMBEDDING_FILENAME
    path.write_bytes(data)
    return path, sha256_bytes(data)


def read_embedding(run_dir: Path | str) -> np.ndarray:
    """Read back a vector written by :func:`write_embedding` (Stage 2 entry)."""
    path = Path(run_dir) / EMBEDDING_FILENAME
    return np.frombuffer(path.read_bytes(), dtype="<f4").astype("float32")


def write_record(run_dir: Path | str, record: Dict[str, Any]) -> Path:
    """Serialise the handoff record deterministically."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / PROBE_FILENAME
    path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def load_record(run_dir: Path | str) -> Dict[str, Any]:
    """Read a handoff record (Stage 2 entry point)."""
    return json.loads((Path(run_dir) / PROBE_FILENAME).read_text(encoding="utf-8"))
