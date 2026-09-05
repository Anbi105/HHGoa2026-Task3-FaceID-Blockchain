"""Quality-gate and encoding tests. All mocked — no model download."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from conftest import make_face, unit_vector
from faceproof.config import cfg
from faceproof.face import (
    EMBEDDING_DIM,
    Probe,
    Rejection,
    _bbox_area,
    _bbox_side,
    _blur_var,
    cosine,
    encode,
    reset_app,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_app()
    yield
    reset_app()


@pytest.fixture
def cv2_ok():
    """Patch cv2 inside face.py so imread succeeds and blur is sharp."""
    with patch("faceproof.face.cv2") as m:
        m.imread.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
        yield m


def _with_blur(value: float):
    return patch("faceproof.face._blur_var", return_value=value)


# ---------------------------------------------------------------------------
# Rejection type
# ---------------------------------------------------------------------------


class TestRejection:
    def test_behaves_as_str(self):
        r = Rejection("image_too_blurry:3.9<45.0", blur_var=3.9)
        assert r == "image_too_blurry:3.9<45.0"
        assert r.startswith("image_too_blurry")
        assert f"{r}" == "image_too_blurry:3.9<45.0"
        assert isinstance(r, str)

    def test_carries_metrics(self):
        r = Rejection("face_too_small:40px<90px", face_px=40.0, n_faces=1)
        assert r.metrics["face_px"] == 40.0
        assert r.metrics["n_faces"] == 1

    def test_code_strips_measurement(self):
        assert Rejection("image_too_blurry:3.9<45.0").code == "image_too_blurry"
        assert Rejection("no_face_detected").code == "no_face_detected"


# ---------------------------------------------------------------------------
# Quality gate — one test per rejection branch
# ---------------------------------------------------------------------------


class TestQualityGate:
    @patch("faceproof.face.cv2")
    def test_unreadable_image(self, mock_cv2):
        mock_cv2.imread.return_value = None
        probe, reason = encode("/nonexistent.jpg")
        assert probe is None
        assert reason == "unreadable_image"

    @patch("faceproof.face.app")
    def test_no_face(self, mock_app, cv2_ok):
        mock_app.return_value.get.return_value = []
        probe, reason = encode("t.jpg")
        assert probe is None
        assert reason == "no_face_detected"
        assert reason.metrics["n_faces"] == 0

    @patch("faceproof.face.app")
    def test_low_detection_confidence(self, mock_app, cv2_ok):
        mock_app.return_value.get.return_value = [make_face(det_score=0.30)]
        with _with_blur(100.0):
            probe, reason = encode("t.jpg")
        assert probe is None
        assert reason.code == "low_detection_confidence"
        # The reason states the threshold it missed, not just the value.
        assert str(cfg.min_det_score) in reason
        assert reason.metrics["det_score"] == pytest.approx(0.30)

    @patch("faceproof.face.app")
    def test_face_too_small(self, mock_app, cv2_ok):
        mock_app.return_value.get.return_value = [make_face(bbox=(100, 100, 150, 200))]
        with _with_blur(100.0):
            probe, reason = encode("t.jpg")
        assert probe is None
        assert reason.code == "face_too_small"
        assert f"<{cfg.min_face_px}px" in reason
        assert reason.metrics["face_px"] == pytest.approx(50.0)

    @patch("faceproof.face.app")
    def test_image_too_blurry(self, mock_app, cv2_ok):
        mock_app.return_value.get.return_value = [make_face()]
        with _with_blur(20.0):
            probe, reason = encode("t.jpg")
        assert probe is None
        assert reason.code == "image_too_blurry"
        assert f"<{cfg.min_blur_var}" in reason
        assert reason.metrics["blur_var"] == pytest.approx(20.0)

    @patch("faceproof.face.app")
    def test_ambiguous_subject(self, mock_app, cv2_ok):
        mock_app.return_value.get.return_value = [
            make_face(bbox=(100, 100, 300, 300), seed=1),
            make_face(bbox=(350, 100, 530, 280), seed=2),
        ]
        with _with_blur(100.0):
            probe, reason = encode("t.jpg")
        assert probe is None
        assert reason.code == "ambiguous_subject"
        assert reason.metrics["n_faces"] == 2
        assert reason.metrics["secondary_ratio"] > cfg.max_secondary_face_ratio

    @patch("faceproof.face.app")
    def test_second_face_small_enough_is_accepted(self, mock_app, cv2_ok):
        """A bystander far smaller than the subject must not block the probe."""
        mock_app.return_value.get.return_value = [
            make_face(bbox=(100, 100, 300, 300), seed=1),
            make_face(bbox=(400, 100, 460, 160), seed=2),  # ratio 0.09
        ]
        with _with_blur(100.0):
            probe, reason = encode("t.jpg")
        assert reason is None
        assert probe.n_faces == 2
        assert probe.secondary_ratio < cfg.max_secondary_face_ratio

    @patch("faceproof.face.app")
    def test_largest_face_is_selected(self, mock_app, cv2_ok):
        """Faces arrive unsorted; the primary must be the largest."""
        big = unit_vector(11)
        mock_app.return_value.get.return_value = [
            make_face(bbox=(0, 0, 60, 60), seed=2),
            make_face(bbox=(100, 100, 340, 340), embedding=big),
        ]
        with _with_blur(100.0):
            probe, reason = encode("t.jpg")
        assert reason is None
        assert np.array_equal(probe.embedding, big)


# ---------------------------------------------------------------------------
# Accepted probe
# ---------------------------------------------------------------------------


class TestValidProbe:
    @patch("faceproof.face.app")
    def test_probe_shape_and_norm(self, mock_app, cv2_ok):
        mock_app.return_value.get.return_value = [make_face(seed=5)]
        with _with_blur(123.5):
            probe, reason = encode("t.jpg")
        assert reason is None
        assert isinstance(probe, Probe)
        assert probe.embedding.shape == (EMBEDDING_DIM,)
        assert probe.embedding.dtype == np.float32
        assert float(np.linalg.norm(probe.embedding)) == pytest.approx(1.0, abs=1e-5)
        assert probe.blur_var == pytest.approx(123.5)
        assert probe.face_px == pytest.approx(200.0)
        assert probe.n_faces == 1

    @patch("faceproof.face.app")
    def test_metrics_dict(self, mock_app, cv2_ok):
        mock_app.return_value.get.return_value = [make_face()]
        with _with_blur(100.0):
            probe, _ = encode("t.jpg")
        m = probe.metrics()
        assert set(m) == {"det_score", "face_px", "blur_var", "n_faces", "secondary_ratio"}

    @patch("faceproof.face.app")
    def test_strict_false_skips_gate(self, mock_app, cv2_ok):
        """Calibration measures without enforcing."""
        mock_app.return_value.get.return_value = [
            make_face(bbox=(100, 100, 130, 130), det_score=0.10)
        ]
        with _with_blur(1.0):
            probe, reason = encode("t.jpg", strict=False)
        assert reason is None
        assert probe.det_score == pytest.approx(0.10)
        assert probe.blur_var == pytest.approx(1.0)

    @patch("faceproof.face.app")
    def test_bad_embedding_shape_rejected(self, mock_app, cv2_ok):
        """A wrong-sized embedding is a rejection, not an assertion.

        `assert` is stripped by `python -O`; this branch must survive it.
        """
        mock_app.return_value.get.return_value = [
            make_face(embedding=np.ones(128, dtype="float32"))
        ]
        with _with_blur(100.0):
            probe, reason = encode("t.jpg")
        assert probe is None
        assert reason.code == "bad_embedding_shape"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestCosine:
    def test_identical(self):
        v = unit_vector(3)
        assert cosine(v, v) == pytest.approx(1.0, abs=1e-5)

    def test_orthogonal(self):
        a, b = np.zeros(512, "float32"), np.zeros(512, "float32")
        a[0], b[1] = 1.0, 1.0
        assert cosine(a, b) == pytest.approx(0.0, abs=1e-6)

    def test_opposite(self):
        v = unit_vector(4)
        assert cosine(v, -v) == pytest.approx(-1.0, abs=1e-5)


class TestHelpers:
    def test_bbox_area(self):
        assert _bbox_area((0, 0, 10, 20)) == 200.0

    def test_bbox_area_inverted_is_zero(self):
        assert _bbox_area((10, 20, 0, 0)) == 0.0

    def test_bbox_side(self):
        assert _bbox_side((0, 0, 10, 20)) == 10.0

    def test_blur_var_empty_crop(self):
        img = np.zeros((10, 10, 3), dtype=np.uint8)
        assert _blur_var(img, (100, 100, 200, 200)) == 0.0

    def test_blur_var_clamps_to_bounds(self):
        """A bbox overhanging the edge must not raise or return garbage."""
        rng = np.random.RandomState(0)
        img = rng.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        assert _blur_var(img, (-50, -50, 150, 150)) > 0.0

    def test_blur_var_sharp_beats_blurred(self):
        rng = np.random.RandomState(1)
        img = rng.randint(0, 255, (200, 200, 3), dtype=np.uint8)
        import cv2

        blurred = cv2.GaussianBlur(img, (31, 31), 12)
        assert _blur_var(img, (0, 0, 200, 200)) > _blur_var(blurred, (0, 0, 200, 200))
