"""Face detection, quality gate, and ArcFace encoding (§5).

Public API
----------
    probe, reason = encode("path/to/image.jpg")

``probe`` is a :class:`Probe` on success (``reason`` is ``None``), or
``None`` on failure — in which case ``reason`` is a :class:`Rejection`,
a plain ``str`` subclass carrying the measurements that produced the
rejection.  Existing string usage (``==``, ``startswith``, f-strings)
keeps working unchanged.

The gate is the interesting part.  Three checks — detector confidence,
absolute face size and Laplacian blur variance — plus an ambiguity check
that rejects images where a second face is comparably large.  Group photos
are the most common realistic input, and silently picking the largest face
is how you produce a confidently wrong result on video.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

from faceproof.config import cfg

EMBEDDING_DIM = 512


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class Rejection(str):
    """A machine-readable rejection reason that also carries its evidence.

    Behaves exactly like the reason string it always was::

        probe, reason = encode(path)
        reason == "no_face_detected"          # True
        reason.startswith("image_too_blurry") # True
        reason.metrics["blur_var"]            # 3.94  ← new

    so the CLI can print the numbers that caused the rejection without
    re-running the detector.
    """

    metrics: Dict[str, Any]

    def __new__(cls, reason: str, **metrics: Any) -> "Rejection":
        obj = super().__new__(cls, reason)
        obj.metrics = dict(metrics)
        return obj

    @property
    def code(self) -> str:
        """The reason without its measured suffix, e.g. ``image_too_blurry``."""
        return self.split(":", 1)[0]


@dataclass
class Probe:
    """Structured face probe for Stage 2 consumption.

    Attributes
    ----------
    embedding : np.ndarray
        512-d float32 L2-normalised ArcFace vector.  Stays on the host.
    bbox : tuple
        Bounding box ``(x1, y1, x2, y2)`` in pixel coordinates.
    det_score : float
        InsightFace detection confidence.
    blur_var : float
        Laplacian variance of the face crop (higher = sharper).
    face_px : float
        Shorter side of the bounding box, in pixels.
    n_faces : int
        Total number of faces detected in the image.
    secondary_ratio : float
        Area of the second-largest face over the primary, or 0.0.
    """

    embedding: np.ndarray
    bbox: tuple
    det_score: float
    blur_var: float
    n_faces: int
    face_px: float = 0.0
    secondary_ratio: float = 0.0

    def metrics(self) -> Dict[str, Any]:
        """Quality measurements, for the manifest and the handoff record."""
        return {
            "det_score": self.det_score,
            "face_px": self.face_px,
            "blur_var": self.blur_var,
            "n_faces": self.n_faces,
            "secondary_ratio": self.secondary_ratio,
        }


# ---------------------------------------------------------------------------
# Lazy model singleton
# ---------------------------------------------------------------------------

_APP = None


def app():
    """Return the InsightFace FaceAnalysis singleton (lazy-loaded)."""
    global _APP
    if _APP is None:
        from insightface.app import FaceAnalysis  # deferred so tests can mock

        _APP = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        _APP.prepare(ctx_id=-1, det_size=(640, 640))  # ctx_id=-1 -> CPU
    return _APP


def preload() -> None:
    """Eagerly load the model — call before the demo recording."""
    app()


def reset_app() -> None:
    """Reset the model singleton (used in tests)."""
    global _APP
    _APP = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _bbox_area(bbox) -> float:
    x1, y1, x2, y2 = bbox[:4]
    return max(0.0, float(x2 - x1)) * max(0.0, float(y2 - y1))


def _bbox_side(bbox) -> float:
    """Shorter side of the bounding box."""
    x1, y1, x2, y2 = bbox[:4]
    return min(max(0.0, float(x2 - x1)), max(0.0, float(y2 - y1)))


def _blur_var(img: np.ndarray, bbox) -> float:
    """Laplacian variance of the face crop, clamped to the image bounds."""
    x1, y1, x2, y2 = [int(v) for v in bbox[:4]]
    h, w = img.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    crop = img[y1:y2, x1:x2]
    if crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


# ---------------------------------------------------------------------------
# Core: encode
# ---------------------------------------------------------------------------


def encode(
    path: str | Path,
    strict: bool = True,
) -> Tuple[Optional[Probe], Optional[Rejection]]:
    """Detect a face, run the quality gate, and return a probe.

    Parameters
    ----------
    path : str | Path
        Path to the input image.
    strict : bool
        If ``True`` (default), apply all quality-gate checks.
        If ``False``, measure but do not enforce (used for calibration).

    Returns
    -------
    (Probe, None) on success, or (None, Rejection) on failure.
    """
    path = Path(path)

    # ── Read image ──────────────────────────────────────────────────
    img = cv2.imread(str(path))
    if img is None:
        return None, Rejection("unreadable_image", path=str(path))

    # ── Detect ──────────────────────────────────────────────────────
    faces = app().get(img)
    if not faces:
        return None, Rejection("no_face_detected", n_faces=0)

    faces = sorted(faces, key=lambda f: _bbox_area(f.bbox), reverse=True)
    primary = faces[0]

    # ── Measure (always, so a rejection can report its own evidence) ─
    det_score = float(primary.det_score)
    face_px = _bbox_side(primary.bbox)
    blur_var = _blur_var(img, primary.bbox)
    primary_area = _bbox_area(primary.bbox)
    secondary_ratio = (
        _bbox_area(faces[1].bbox) / primary_area
        if len(faces) > 1 and primary_area > 0
        else 0.0
    )
    measured: Dict[str, Any] = {
        "det_score": det_score,
        "face_px": face_px,
        "blur_var": blur_var,
        "n_faces": len(faces),
        "secondary_ratio": secondary_ratio,
    }

    # ── Quality gate — each reason states the value AND the threshold ─
    if strict:
        if det_score < cfg.min_det_score:
            return None, Rejection(
                f"low_detection_confidence:{det_score:.3f}<{cfg.min_det_score}", **measured
            )
        if face_px < cfg.min_face_px:
            return None, Rejection(
                f"face_too_small:{int(face_px)}px<{cfg.min_face_px}px", **measured
            )
        if blur_var < cfg.min_blur_var:
            return None, Rejection(
                f"image_too_blurry:{blur_var:.1f}<{cfg.min_blur_var}", **measured
            )
        if secondary_ratio > cfg.max_secondary_face_ratio:
            return None, Rejection(
                f"ambiguous_subject:{len(faces)}_faces_ratio_{secondary_ratio:.2f}"
                f">{cfg.max_secondary_face_ratio}",
                **measured,
            )

    # ── Build probe ─────────────────────────────────────────────────
    embedding = np.ascontiguousarray(primary.normed_embedding, dtype="float32")
    if embedding.shape != (EMBEDDING_DIM,):
        return None, Rejection(
            f"bad_embedding_shape:{embedding.shape}", **measured
        )

    return (
        Probe(
            embedding=embedding,
            bbox=tuple(float(v) for v in primary.bbox[:4]),
            det_score=det_score,
            blur_var=blur_var,
            n_faces=len(faces),
            face_px=face_px,
            secondary_ratio=secondary_ratio,
        ),
        None,
    )


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two L2-normalised vectors.

    Because the vectors are already unit length, this is the dot product.
    """
    return float(np.dot(a, b))
