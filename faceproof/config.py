"""Single source of configuration for the FaceProof pipeline.

All tunables live here.  Every value can be overridden by an environment
variable prefixed with ``FACEPROOF_`` (see ``.env.example``).

The config is echoed into the run manifest at the start of every run, so
the recording shows exactly which parameters produced the result.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Field names whose values must never be printed or written to the manifest.
_SECRET_FIELDS: tuple[str, ...] = ("serpapi_key", "private_key")

# Secrets Stage 3 reads straight from the environment rather than from this
# dataclass (see faceproof/chain.py).  `public()` reports presence only.
_ENV_SECRET_VARS: tuple[str, ...] = ("PRIVATE_KEY", "SERPAPI_KEY")


def _display_path(p: Path) -> str:
    """Repo-relative when the path is inside the repo, absolute otherwise.

    `public()` is copied into probe.json; an absolute path there leaks the
    operator's home directory into an artifact meant to be shown on camera.
    """
    try:
        return str(p.resolve().relative_to(_REPO_ROOT)).replace("\\", "/")
    except (ValueError, OSError):
        return str(p)


def _env(key: str, default: str) -> str:
    return os.environ.get(f"FACEPROOF_{key}", default)


def _env_float(key: str, default: float) -> float:
    return float(_env(key, str(default)))


def _calibrated_accept_at() -> Optional[float]:
    """``suggested_accept_at`` from ``data/calibration.json``, if measured.

    ``calibrate.py`` writes that file but nothing read it, so a team that did
    the calibration work still ran the pipeline on the 0.55 placeholder and
    the recording would cite a number the gate was not using (guide D3).
    Person 2's config already resolved this the same way; this brings the
    integrated config in line.  An explicit ``FACEPROOF_ACCEPT_AT`` still wins,
    and a missing or malformed file falls back silently to the default.
    """
    path = Path(_env("DATA_DIR", str(_REPO_ROOT / "data"))) / "calibration.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))["suggested_accept_at"]
        return float(value)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _accept_at_default() -> float:
    explicit = os.environ.get("FACEPROOF_ACCEPT_AT")
    if explicit is not None:
        return float(explicit)
    measured = _calibrated_accept_at()
    return measured if measured is not None else 0.55


def _env_int(key: str, default: int) -> int:
    return int(_env(key, str(default)))


@dataclass(frozen=True)
class Config:
    """Immutable pipeline configuration."""

    # ── Model identity: goes into the evidence bundle verbatim ──────
    model_id: str = "insightface/buffalo_l@w600k_r50"
    pipeline_version: str = "faceproof/1.1.0"
    schema_id: str = "faceproof.evidence.v1"
    probe_schema_id: str = "faceproof.probe.v1"

    # ── Quality-gate thresholds (§5) ────────────────────────────────
    min_det_score: float = field(default_factory=lambda: _env_float("MIN_DET_SCORE", 0.62))
    min_face_px: int = field(default_factory=lambda: _env_int("MIN_FACE_PX", 90))
    min_blur_var: float = field(default_factory=lambda: _env_float("MIN_BLUR_VAR", 45.0))
    max_secondary_face_ratio: float = field(
        default_factory=lambda: _env_float("MAX_SECONDARY_FACE_RATIO", 0.60)
    )

    # ── Matching (§6) — set accept_at from calibrate.py, do NOT guess ──
    accept_at: float = field(default_factory=_accept_at_default)
    review_at: float = field(default_factory=lambda: _env_float("REVIEW_AT", 0.42))
    min_margin: float = field(default_factory=lambda: _env_float("MIN_MARGIN", 0.06))
    top_k: int = field(default_factory=lambda: _env_int("TOP_K", 10))
    phash_max_hamming: int = field(default_factory=lambda: _env_int("PHASH_MAX_HAMMING", 10))

    # ── Consent (§8, D12) ───────────────────────────────────────────
    consent_scope: str = field(default_factory=lambda: _env("CONSENT_SCOPE", "face_probe_demo"))
    consent_ttl_days: int = field(default_factory=lambda: _env_int("CONSENT_TTL_DAYS", 30))

    # ── Serialisation (§7, D9) ──────────────────────────────────────
    float_precision: int = field(default_factory=lambda: _env_int("FLOAT_PRECISION", 6))

    # ── Paths ───────────────────────────────────────────────────────
    data_dir: Path = field(
        default_factory=lambda: Path(_env("DATA_DIR", str(_REPO_ROOT / "data")))
    )
    out_dir: Path = field(
        default_factory=lambda: Path(_env("OUT_DIR", str(_REPO_ROOT / "out")))
    )

    # ── Derived paths ───────────────────────────────────────────────
    @property
    def calib_dir(self) -> Path:
        return self.data_dir / "calib"

    @property
    def calibration_json(self) -> Path:
        return self.data_dir / "calibration.json"

    @property
    def consent_dir(self) -> Path:
        """Holds per-subject salts — secret, never committed."""
        return self.data_dir / "consent"

    @property
    def consent_store(self) -> Path:
        return self.consent_dir / "store.json"

    def run_dir(self, run_id: str) -> Path:
        return self.out_dir / f"run-{run_id}"

    # ── Presentation ────────────────────────────────────────────────
    def public(self) -> Dict[str, Any]:
        """Config minus secrets — safe to print and to commit to the manifest.

        Two things are deliberately not the raw dataclass dump:

        * ``_SECRET_FIELDS`` are masked if they are ever added as real fields
          (see ``TestPublic.test_masks_secret_fields``);
        * Stage 3 keeps its secrets in the environment rather than on this
          dataclass, so that masking alone would report nothing about them.
          ``env_secrets`` closes that gap — presence only, never a value.

        Paths are rendered relative to the repo root where possible: this dict
        is copied verbatim into ``probe.json``, and an absolute path leaks the
        operator's home directory into an artifact meant to be shown.
        """
        d: Dict[str, Any] = {}
        for k, v in asdict(self).items():
            if k in _SECRET_FIELDS:
                d[k] = "<set>" if v else "<unset>"
            elif isinstance(v, Path):
                d[k] = _display_path(v)
            else:
                d[k] = v
        d["env_secrets"] = {
            name.lower(): "<set>" if os.environ.get(name) else "<unset>"
            for name in _ENV_SECRET_VARS
        }
        return d


# Module-level singleton — importable as ``from faceproof.config import cfg``
cfg = Config()


def banner() -> str:
    """Deterministic JSON rendering of the public config."""
    return json.dumps(cfg.public(), indent=2, sort_keys=True)
