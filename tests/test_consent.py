"""Consent, commitments, and the erasure path."""

from __future__ import annotations

import json
import os
import uuid
from datetime import timedelta

import numpy as np
import pytest

from conftest import unit_vector
from faceproof.config import cfg
from faceproof.consent import (
    SALT_BYTES,
    ConsentRecord,
    ConsentStore,
    _iso,
    _now,
    check,
    embedding_bytes,
    embedding_commitment,
    fresh_salt,
    grant,
    subject_commitment,
    validate,
)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


class TestGrant:
    def test_fields(self):
        rec = grant("alice", scope="face_probe_demo")
        assert rec.subject_id == "alice"
        assert rec.scope == "face_probe_demo"
        assert uuid.UUID(rec.token, version=4)
        assert rec.salt is not None and len(rec.salt) == SALT_BYTES
        assert rec.revoked_at is None

    def test_strips_whitespace(self):
        assert grant("  alice  ").subject_id == "alice"

    def test_empty_subject_rejected(self):
        with pytest.raises(ValueError):
            grant("   ")

    def test_expiry_is_set(self):
        rec = grant("alice", ttl_days=7)
        assert rec.expires_at > rec.granted_at

    def test_each_grant_has_a_distinct_salt_and_token(self):
        a, b = grant("alice"), grant("alice")
        assert a.token != b.token
        assert a.salt != b.salt


class TestCheck:
    def test_valid(self):
        assert check(grant("alice")) == (True, "ok")
        assert validate(grant("alice")) is True

    def test_none(self):
        ok, reason = check(None)
        assert not ok and reason == "no_consent_on_record"

    def test_expired(self):
        rec = grant("alice")
        rec.expires_at = _iso(_now() - timedelta(days=1))
        ok, reason = check(rec)
        assert not ok and reason.startswith("consent_expired")

    def test_not_yet_valid(self):
        rec = grant("alice")
        rec.granted_at = _iso(_now() + timedelta(days=1))
        ok, reason = check(rec)
        assert not ok and reason == "consent_not_yet_valid"

    def test_scope_mismatch(self):
        rec = grant("alice", scope="research")
        ok, reason = check(rec, scope="face_probe_demo")
        assert not ok and reason.startswith("scope_mismatch")

    def test_malformed_token(self):
        rec = grant("alice")
        rec.token = "not-a-uuid"
        ok, reason = check(rec)
        assert not ok and reason == "malformed_consent_token"

    def test_missing_subject(self):
        rec = grant("alice")
        rec.subject_id = ""
        assert check(rec)[1] == "missing_subject_id"

    def test_revoked(self):
        rec = grant("alice")
        rec.revoked_at = _iso(_now())
        assert check(rec)[1].startswith("consent_revoked")

    def test_salt_erased(self):
        rec = grant("alice")
        rec.salt_hex = None
        assert check(rec)[1] == "consent_salt_erased"

    def test_malformed_timestamps(self):
        rec = grant("alice")
        rec.expires_at = "not-a-date"
        assert check(rec)[1] == "malformed_expires_at"


# ---------------------------------------------------------------------------
# Commitments
# ---------------------------------------------------------------------------


class TestCommitments:
    def test_subject_commitment_is_32_bytes(self):
        assert len(subject_commitment(grant("alice"))) == 32

    def test_subject_commitment_depends_only_on_token(self):
        a = grant("alice")
        b = ConsentRecord(
            subject_id="totally-different", scope="other", token=a.token,
            salt_hex=os.urandom(32).hex(),
        )
        assert subject_commitment(a) == subject_commitment(b)

    def test_subject_commitment_leaks_no_subject_id(self):
        a, b = grant("alice"), grant("alice")
        assert subject_commitment(a) != subject_commitment(b)

    def test_embedding_commitment_length(self):
        c, salt = embedding_commitment(unit_vector(1))
        assert len(c) == 32 and len(salt) == SALT_BYTES

    def test_deterministic_for_fixed_salt(self):
        e, salt = unit_vector(1), fresh_salt()
        assert embedding_commitment(e, salt)[0] == embedding_commitment(e, salt)[0]

    def test_salt_changes_commitment(self):
        e = unit_vector(1)
        assert embedding_commitment(e)[0] != embedding_commitment(e)[0]

    def test_embedding_changes_commitment(self):
        salt = fresh_salt()
        assert (
            embedding_commitment(unit_vector(1), salt)[0]
            != embedding_commitment(unit_vector(2), salt)[0]
        )

    def test_bad_salt_length_raises_valueerror(self):
        """Not AssertionError — `assert` is stripped under `python -O`."""
        with pytest.raises(ValueError):
            embedding_commitment(unit_vector(1), salt=b"short")


class TestEmbeddingBytes:
    def test_little_endian_regardless_of_input_order(self):
        v = unit_vector(3)
        assert embedding_bytes(v) == embedding_bytes(v.astype(">f4"))

    def test_length(self):
        assert len(embedding_bytes(unit_vector(3))) == 512 * 4

    def test_non_contiguous_input(self):
        wide = np.zeros((512, 2), dtype="float32")
        wide[:, 0] = unit_vector(3)
        assert embedding_bytes(wide[:, 0]) == embedding_bytes(unit_vector(3))


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class TestStore:
    def test_grant_persists(self, tmp_path):
        path = tmp_path / "store.json"
        rec = ConsentStore(path).grant("alice")
        reloaded = ConsentStore(path).get("alice")
        assert reloaded.token == rec.token
        assert reloaded.salt == rec.salt

    def test_missing_subject(self, tmp_path):
        assert ConsentStore(tmp_path / "s.json").get("nobody") is None

    def test_list_is_sorted(self, tmp_path):
        s = ConsentStore(tmp_path / "s.json")
        for name in ("carol", "alice", "bob"):
            s.grant(name)
        assert [r.subject_id for r in s.list()] == ["alice", "bob", "carol"]

    def test_file_permissions_are_owner_only(self, tmp_path):
        path = tmp_path / "s.json"
        ConsentStore(path).grant("alice")
        assert oct(path.stat().st_mode)[-3:] == "600"

    def test_empty_store_loads(self, tmp_path):
        assert len(ConsentStore(tmp_path / "absent.json")) == 0

    # ── Erasure ─────────────────────────────────────────────────────

    def test_revoke_destroys_salt(self, tmp_path):
        path = tmp_path / "s.json"
        store = ConsentStore(path)
        store.grant("alice")
        rec = store.revoke("alice")

        assert rec.salt is None
        assert rec.revoked_at is not None
        # …and it is gone from disk, not just from memory.
        assert "salt_hex" in json.loads(path.read_text())["subjects"]["alice"]
        assert json.loads(path.read_text())["subjects"]["alice"]["salt_hex"] is None
        assert ConsentStore(path).get("alice").salt is None

    def test_revoke_blocks_future_probes(self, tmp_path):
        store = ConsentStore(tmp_path / "s.json")
        store.grant("alice")
        store.revoke("alice")
        ok, reason = check(store.get("alice"))
        assert not ok and reason.startswith("consent_revoked")

    def test_revoke_keeps_an_audit_trail(self, tmp_path):
        """The record survives revocation so the withdrawal is auditable."""
        store = ConsentStore(tmp_path / "s.json")
        store.grant("alice")
        store.revoke("alice")
        assert "alice" in store
        assert store.get("alice").granted_at

    def test_revoke_unknown_subject(self, tmp_path):
        assert ConsentStore(tmp_path / "s.json").revoke("nobody") is None

    def test_commitment_unverifiable_after_erasure(self, tmp_path):
        """The point of the whole design: an anchored commitment cannot be
        reproduced once the salt is destroyed."""
        store = ConsentStore(tmp_path / "s.json")
        rec = store.grant("alice")
        embedding = unit_vector(9)
        anchored, _ = embedding_commitment(embedding, salt=rec.salt)

        store.revoke("alice")
        erased = store.get("alice")
        assert erased.salt is None

        # Anyone re-running the commitment now must guess a 256-bit salt.
        guess, _ = embedding_commitment(embedding)
        assert guess != anchored
