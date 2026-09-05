"""Calibration tests.

These drive ``calibrate.run()`` itself through an injected encoder, so a
change to the threshold rule fails a test.  The previous version of this
file re-implemented the arithmetic inline and asserted against its own
expression, which meant ``run()`` had no test at all.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from conftest import make_probe, unit_vector
from faceproof.calibrate import (
    SAFETY_MARGIN,
    CalibrationResult,
    _compute_pairs,
    _discover_subjects,
    _fingerprint,
    main,
    run,
    write_json,
)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestDiscovery:
    def test_finds_subjects(self, calib_tree):
        root = calib_tree({"alice": 3, "bob": 2})
        found = _discover_subjects(root)
        assert set(found) == {"alice", "bob"}
        assert len(found["alice"]) == 3

    def test_missing_dir_is_empty(self, tmp_path):
        assert _discover_subjects(tmp_path / "nope") == {}

    def test_ignores_non_images(self, calib_tree):
        root = calib_tree({"alice": 2})
        (root / "alice" / "notes.txt").write_text("hi")
        assert len(_discover_subjects(root)["alice"]) == 2

    def test_ignores_loose_files(self, calib_tree):
        root = calib_tree({"alice": 2, "bob": 2})
        (root / "stray.jpg").write_bytes(b"\xff\xd8\xff")
        assert set(_discover_subjects(root)) == {"alice", "bob"}


class TestFingerprint:
    def test_stable_across_calls(self, calib_tree):
        root = calib_tree({"alice": 2, "bob": 2})
        subjects = _discover_subjects(root)
        assert _fingerprint(subjects) == _fingerprint(subjects)

    def test_changes_with_content(self, calib_tree):
        root = calib_tree({"alice": 2, "bob": 2})
        before = _fingerprint(_discover_subjects(root))
        (root / "alice" / "00.jpg").write_bytes(b"\xff\xd8\xff\x00different")
        assert _fingerprint(_discover_subjects(root)) != before


# ---------------------------------------------------------------------------
# Pair generation
# ---------------------------------------------------------------------------


class TestComputePairs:
    def _encoded(self):
        return {
            "a": [make_probe(seed=1), make_probe(seed=2), make_probe(seed=3)],
            "b": [make_probe(seed=11), make_probe(seed=12), make_probe(seed=13)],
        }

    def test_counts(self):
        genuine, impostor = _compute_pairs(self._encoded())
        assert len(genuine) == 6   # C(3,2) per subject
        assert len(impostor) == 9  # 3 x 3 across

    def test_three_subjects(self):
        enc = self._encoded()
        enc["c"] = [make_probe(seed=21), make_probe(seed=22)]
        genuine, impostor = _compute_pairs(enc)
        assert len(genuine) == 3 + 3 + 1
        assert len(impostor) == 9 + 6 + 6

    def test_scores_are_floats(self):
        genuine, impostor = _compute_pairs(self._encoded())
        assert all(isinstance(s, float) for s in genuine + impostor)

    def test_identical_embeddings_score_one(self):
        v = unit_vector(7)
        enc = {"a": [make_probe(embedding=v), make_probe(embedding=v)]}
        genuine, _ = _compute_pairs(enc)
        assert genuine[0] == pytest.approx(1.0, abs=1e-5)


# ---------------------------------------------------------------------------
# run() — the real thing
# ---------------------------------------------------------------------------


class TestRun:
    def test_happy_path(self, calib_tree, fake_encoder):
        root = calib_tree({"alice": 4, "bob": 4, "carol": 4})
        result = run(root, encoder=fake_encoder)

        assert result.ok
        assert result.error is None
        assert result.n_subjects == 3
        assert result.n_images == 12
        assert result.genuine_n == 3 * 6
        assert result.impostor_n == 3 * 16
        assert result.dataset_fingerprint

    def test_threshold_follows_the_rule(self, calib_tree, fake_encoder):
        """accept_at = impostor_max + SAFETY_MARGIN, measured from run()."""
        root = calib_tree({"alice": 4, "bob": 4})
        result = run(root, encoder=fake_encoder)
        assert result.suggested_accept_at == pytest.approx(
            max(result.impostor_scores) + SAFETY_MARGIN
        )

    def test_no_impostor_is_accepted_at_the_threshold(self, calib_tree, fake_encoder):
        root = calib_tree({"alice": 4, "bob": 4, "carol": 4})
        result = run(root, encoder=fake_encoder)
        assert result.false_accept_rate == 0.0

    def test_true_accept_rate_matches_distribution(self, calib_tree, fake_encoder):
        root = calib_tree({"alice": 4, "bob": 4})
        result = run(root, encoder=fake_encoder)
        expected = float(
            (np.array(result.genuine_scores) >= result.suggested_accept_at).mean()
        )
        assert result.true_accept_rate == pytest.approx(expected)

    def test_separation_and_overlap_flag_agree(self, calib_tree, fake_encoder):
        root = calib_tree({"alice": 4, "bob": 4})
        result = run(root, encoder=fake_encoder)
        assert result.separation == pytest.approx(
            result.genuine_min - result.impostor_max
        )
        assert result.overlap_warning == (result.genuine_min <= result.impostor_max)

    def test_clustered_subjects_separate(self, calib_tree, fake_encoder):
        """Sanity: the synthetic clusters must actually be separable,
        otherwise the other assertions prove nothing."""
        root = calib_tree({"alice": 5, "bob": 5, "carol": 5})
        result = run(root, encoder=fake_encoder)
        assert result.genuine_mean > result.impostor_mean
        assert not result.overlap_warning
        assert result.separation > 0

    # ── Error paths ─────────────────────────────────────────────────

    def test_needs_two_subjects(self, calib_tree, fake_encoder):
        result = run(calib_tree({"alice": 5}), encoder=fake_encoder)
        assert not result.ok
        assert "2 subjects" in result.error

    def test_needs_two_images_each(self, calib_tree, fake_encoder):
        result = run(calib_tree({"alice": 1, "bob": 1}), encoder=fake_encoder)
        assert not result.ok
        assert result.error

    def test_missing_directory(self, tmp_path, fake_encoder):
        result = run(tmp_path / "absent", encoder=fake_encoder)
        assert not result.ok

    def test_unusable_images_are_skipped(self, calib_tree, fake_encoder):
        root = calib_tree({"alice": 3, "bob": 3})
        (root / "alice" / "noface.jpg").write_bytes(b"\xff\xd8\xff")
        result = run(root, encoder=fake_encoder)
        assert result.ok
        assert result.n_skipped == 1
        assert result.n_images == 6

    def test_subject_drops_out_when_too_many_skips(self, calib_tree, fake_encoder):
        root = calib_tree({"bob": 4, "carol": 4})
        root_a = root / "alice"
        root_a.mkdir()
        for n in ("noface_1.jpg", "noface_2.jpg"):
            (root_a / n).write_bytes(b"\xff\xd8\xff")
        result = run(root, encoder=fake_encoder)
        assert result.ok
        assert result.n_subjects == 2  # alice dropped: no usable probes


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


class TestWriteJson:
    def test_round_trip(self, calib_tree, fake_encoder, tmp_path):
        result = run(calib_tree({"alice": 3, "bob": 3}), encoder=fake_encoder)
        path = write_json(result, tmp_path / "calibration.json")
        data = json.loads(path.read_text())

        assert data["schema"] == "faceproof.calibration.v1"
        assert data["suggested_accept_at"] == pytest.approx(
            round(result.suggested_accept_at, 4)
        )
        assert data["dataset"]["n_subjects"] == 2
        assert data["dataset"]["fingerprint"] == result.dataset_fingerprint
        assert data["model_id"]

    def test_records_full_distributions(self, calib_tree, fake_encoder, tmp_path):
        """The score lists are the 'show the losers' evidence — they must
        survive into the committed artifact."""
        result = run(calib_tree({"alice": 3, "bob": 3}), encoder=fake_encoder)
        data = json.loads(write_json(result, tmp_path / "c.json").read_text())
        assert len(data["genuine"]["scores"]) == result.genuine_n
        assert len(data["impostor"]["scores"]) == result.impostor_n
        assert data["impostor"]["scores"] == sorted(
            data["impostor"]["scores"], reverse=True
        )

    def test_empty_result_serialises(self, tmp_path):
        data = json.loads(
            write_json(CalibrationResult(), tmp_path / "c.json").read_text()
        )
        assert data["genuine"]["n"] == 0


class TestMain:
    def test_exit_1_without_data(self, tmp_path, capsys):
        assert main([str(tmp_path / "absent")]) == 1

    def test_exit_0_and_writes(self, calib_tree, fake_encoder, tmp_path, monkeypatch):
        import faceproof.calibrate as cal

        root = calib_tree({"alice": 3, "bob": 3})
        monkeypatch.setattr(cal, "encode", fake_encoder)
        out = tmp_path / "calibration.json"
        assert main([str(root), str(out)]) == 0
        assert json.loads(out.read_text())["dataset"]["n_subjects"] == 2
