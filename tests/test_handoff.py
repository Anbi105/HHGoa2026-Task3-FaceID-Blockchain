"""Stage 1 → Stage 2 boundary artifact tests."""

from __future__ import annotations

import json

import numpy as np
import pytest

from conftest import make_probe, unit_vector
from faceproof.config import cfg
from faceproof.consent import ConsentStore, embedding_commitment
from faceproof.face import Rejection
from faceproof.handoff import (
    _reject_floats,
    build_record,
    load_record,
    q,
    read_embedding,
    write_embedding,
    write_record,
)


@pytest.fixture
def consent(tmp_path):
    return ConsentStore(tmp_path / "store.json").grant("alice")


@pytest.fixture
def image(tmp_path):
    p = tmp_path / "photo.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0 not really a jpeg")
    return p


class TestQuantise:
    def test_fixed_precision_string(self):
        assert q(0.1 + 0.2) == "0.300000"
        assert q(1) == "1.000000"

    def test_precision_override(self):
        assert q(3.14159, 2) == "3.14"

    def test_stable_across_equal_values(self):
        assert q(1 / 3) == q(0.3333333333333333)


class TestRejectFloats:
    def test_accepts_clean_record(self):
        _reject_floats({"a": "1.0", "b": [1, "2"], "c": {"d": None}})

    def test_rejects_nested_float(self):
        with pytest.raises(TypeError, match=r"\$\.a\.b\[1\]"):
            _reject_floats({"a": {"b": [1, 2.5]}})


class TestAcceptedRecord:
    def test_shape(self, consent, image):
        probe = make_probe(seed=1)
        rec = build_record("run1", image, consent, probe=probe, embedding_digest="ab" * 32)

        assert rec["schema_id"] == cfg.probe_schema_id
        assert rec["status"] == "accepted"
        assert rec["rejection_reason"] is None
        assert rec["run_id"] == "run1"
        assert rec["image"]["filename"] == "photo.jpg"
        assert rec["image"]["sha256"]

    def test_no_raw_floats_anywhere(self, consent, image):
        """D9: a float in the record is the classic cause of a proof that
        verifies locally and fails against chain."""
        rec = build_record("run1", image, consent, probe=make_probe(seed=1))
        _reject_floats(rec)  # raises if any survived

    def test_commitment_matches_salt(self, consent, image):
        probe = make_probe(seed=1)
        rec = build_record("run1", image, consent, probe=probe)
        expected, _ = embedding_commitment(probe.embedding, salt=consent.salt)
        assert rec["embedding"]["commitment"] == "0x" + expected.hex()

    def test_carries_no_biometrics_or_pii(self, consent, image):
        rec = build_record("run1", image, consent, probe=make_probe(seed=1))
        blob = json.dumps(rec)
        assert "alice" not in blob            # no subject id
        assert consent.token not in blob      # no consent token
        assert consent.salt_hex not in blob   # no salt
        assert "embedding" in rec and isinstance(rec["embedding"]["commitment"], str)

    def test_records_the_gate_that_was_applied(self, consent, image):
        rec = build_record("run1", image, consent, probe=make_probe(seed=1))
        assert rec["quality_gate"]["min_face_px"] == cfg.min_face_px
        assert rec["quality_gate"]["min_blur_var"] == q(cfg.min_blur_var)

    def test_refuses_when_salt_erased(self, tmp_path, image):
        store = ConsentStore(tmp_path / "s.json")
        store.grant("alice")
        erased = store.revoke("alice")
        with pytest.raises(ValueError, match="erased"):
            build_record("run1", image, erased, probe=make_probe(seed=1))


class TestRejectedRecord:
    def test_abstain_is_recorded(self, consent, image):
        rejection = Rejection(
            "image_too_blurry:3.9<45.0",
            det_score=0.80, face_px=104.0, blur_var=3.9, n_faces=1, secondary_ratio=0.0,
        )
        rec = build_record("run1", image, consent, rejection=rejection)
        assert rec["status"] == "rejected"
        assert rec["rejection_reason"] == "image_too_blurry:3.9<45.0"
        assert rec["quality"]["blur_var"] == q(3.9)
        assert rec["embedding"]["commitment"] is None
        _reject_floats(rec)

    def test_sparse_metrics(self, consent, image):
        rec = build_record(
            "run1", image, consent, rejection=Rejection("no_face_detected", n_faces=0)
        )
        assert rec["quality"]["blur_var"] is None
        assert rec["quality"]["n_faces"] == 0

    def test_rejected_run_still_works_without_salt(self, tmp_path, image):
        """An abstain makes no commitment, so it must not need the salt."""
        store = ConsentStore(tmp_path / "s.json")
        store.grant("alice")
        erased = store.revoke("alice")
        rec = build_record(
            "run1", image, erased, rejection=Rejection("no_face_detected", n_faces=0)
        )
        assert rec["status"] == "rejected"


class TestRoundTrip:
    def test_embedding_bytes_survive(self, tmp_path):
        v = unit_vector(3)
        path, digest = write_embedding(tmp_path, v)
        assert path.stat().st_size == 512 * 4
        assert np.allclose(read_embedding(tmp_path), v)

    def test_digest_is_of_the_written_bytes(self, tmp_path):
        from faceproof.manifest import sha256_file

        _, digest = write_embedding(tmp_path, unit_vector(3))
        assert digest == sha256_file(tmp_path / "embedding.f32")

    def test_record_round_trip(self, tmp_path, consent, image):
        rec = build_record("run1", image, consent, probe=make_probe(seed=1))
        write_record(tmp_path, rec)
        assert load_record(tmp_path) == rec

    def test_record_is_deterministic(self, tmp_path, consent, image):
        """Two writes of the same record produce identical bytes."""
        rec = build_record("run1", image, consent, probe=make_probe(seed=1))
        a = write_record(tmp_path / "a", rec).read_bytes()
        b = write_record(tmp_path / "b", rec).read_bytes()
        assert a == b
