"""Shared fixtures. No InsightFace model or network access is required."""

from __future__ import annotations

import itertools
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import numpy as np
import pytest

from faceproof.face import Probe


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path):
    """Point every filesystem-touching config path at a temp dir.

    Without this a test run would write into the real data/ and out/
    directories — and, worse, could read a developer's real consent store.

    ``Config`` is a frozen dataclass and every module holds a reference to
    the same ``cfg`` singleton, so the swap goes through
    ``object.__setattr__`` and is undone on teardown.
    """
    from faceproof.config import cfg

    saved = {k: getattr(cfg, k) for k in ("data_dir", "out_dir")}
    object.__setattr__(cfg, "data_dir", tmp_path / "data")
    object.__setattr__(cfg, "out_dir", tmp_path / "out")
    try:
        yield tmp_path
    finally:
        for k, v in saved.items():
            object.__setattr__(cfg, k, v)


def unit_vector(seed: int, dim: int = 512) -> np.ndarray:
    v = np.random.RandomState(seed).randn(dim).astype("float32")
    return (v / np.linalg.norm(v)).astype("float32")


def cluster_vector(base_seed: int, jitter_seed: int, spread: float = 0.25) -> np.ndarray:
    """A vector near ``base_seed``'s direction — a synthetic 'same subject'."""
    base = unit_vector(base_seed)
    noise = unit_vector(jitter_seed)
    v = base + spread * noise
    return (v / np.linalg.norm(v)).astype("float32")


def make_probe(embedding=None, seed: int = 0, **kw) -> Probe:
    defaults = dict(
        embedding=unit_vector(seed) if embedding is None else embedding,
        bbox=(100.0, 100.0, 300.0, 300.0),
        det_score=0.95,
        blur_var=100.0,
        n_faces=1,
        face_px=200.0,
        secondary_ratio=0.0,
    )
    defaults.update(kw)
    return Probe(**defaults)


def make_face(bbox=(100, 100, 300, 300), det_score=0.95, embedding=None, seed=0):
    """A stand-in for an InsightFace face object."""
    return SimpleNamespace(
        bbox=np.array(bbox, dtype="float32"),
        det_score=det_score,
        normed_embedding=unit_vector(seed) if embedding is None else embedding,
    )


@pytest.fixture
def fake_encoder():
    """An ``encode``-shaped callable driven by the directory layout.

    ``data/calib/<subject>/<n>.jpg`` yields a vector clustered on the
    subject, so calibration can be exercised end to end without a model.
    """
    from faceproof.face import Rejection

    subject_seeds: dict[str, int] = {}

    def _encode(path, strict: bool = True):
        path = Path(path)
        if "unreadable" in path.name:
            return None, Rejection("unreadable_image")
        if "noface" in path.name:
            return None, Rejection("no_face_detected", n_faces=0)
        subject = path.parent.name
        seed = subject_seeds.setdefault(subject, 1000 + 500 * len(subject_seeds))
        idx = abs(hash(path.name)) % 997
        return make_probe(embedding=cluster_vector(seed, seed + 1 + idx)), None

    return _encode


@pytest.fixture
def calib_tree(tmp_path):
    """Build a calibration directory of empty files; content is irrelevant
    because the encoder is injected."""

    def _build(spec: dict[str, int]) -> Path:
        root = tmp_path / "calib"
        for subject, n in spec.items():
            d = root / subject
            d.mkdir(parents=True, exist_ok=True)
            for i in range(n):
                (d / f"{i:02d}.jpg").write_bytes(b"\xff\xd8\xff")  # JPEG magic
        return root

    return _build
