"""Regressions for the audit blockers fixed on `fix/audit-blockers`.

Each test pins one previously-broken behaviour:

#1  selective-disclosure checks must FAIL on a tampered bundle (they were
    tautologies verifying a fresh proof against its own fresh tree)
#2  merkle.verify / verifyField must reject a wrong-length audit path
    (a short path passed an internal node off as a group leaf)
#3  anchor() must raise on a reverted (status != 1) transaction
#4  the consent group carries keccak256(consent_token) once, not twice
#5  the Stage 2 bridge must ABSTAIN, not emit an empty positive match, when
    the winning channel has no locatable record
#6  stage2_adapter must not turn `accept_at` (a score) into a timestamp
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from faceproof.bundle import (
    TREE_DEPTH,
    assemble_bundle,
    assemble_groups,
    build_proofs,
    canonical_leaves,
)
from faceproof.canonical import canon, q
from faceproof.merkle import build, root as merkle_root, unhex, verify
from faceproof.stage2_adapter import normalize


# --------------------------------------------------------------------------- #
# shared fixtures
# --------------------------------------------------------------------------- #

def _stage1():
    return {
        "status": "accepted",
        "model_id": "insightface/buffalo_l@w600k_r50",
        "pipeline_version": "faceproof/1.1.0",
        "quality": {"det_score": q(0.95), "blur_var": q(70.0)},
        "consent": {
            "subject_commitment": "0x" + "ab" * 32,
            "granted_at": "2026-09-06T10:00:00Z",
            "scope": "face_probe_demo",
        },
        "embedding": {"commitment": "0x" + "cd" * 32},
    }


def _stage2():
    return normalize(
        {
            "fusion_outcome": "CORROBORATED",
            "snapshot_id": "snap-001",
            "margin": 0.2,
            "match": {
                "platform": "bluesky",
                "post_url": "https://bsky.app/profile/x.bsky.social/post/3k",
                "post_uri": "at://did:plc:x/app.bsky.feed.post/3k",
                "author_did": "did:plc:x",
                "author_handle": "x.bsky.social",
                "text": "hello",
                "image_sha256": "ef" * 32,
                "phash": "12345678",
                "score": 0.9,
            },
        },
        source="test",
    )


# --------------------------------------------------------------------------- #
# #1 - selective disclosure is no longer a tautology
# --------------------------------------------------------------------------- #

def test_selective_disclosure_fails_on_tampered_bundle(tmp_path):
    from faceproof.verify import verify_bundle_locally

    bundle, proofs = assemble_bundle(tmp_path, _stage1(), _stage2())

    clean = verify_bundle_locally(bundle, proofs)
    assert clean["selective_disclosure_regenerated"] is True
    assert clean["selective_disclosure_stored_proof"] is True
    assert clean["selective_disclosure_pass"] is True

    # flip one character in the disclosed group; anchored merkle_root stays
    bundle["groups"]["match_location"]["post_url"] += "x"
    tampered = verify_bundle_locally(bundle, proofs)
    assert tampered["root_match"] is False
    assert tampered["selective_disclosure_regenerated"] is False   # was always True
    assert tampered["selective_disclosure_stored_proof"] is False
    assert tampered["selective_disclosure_pass"] is False


def test_selective_disclosure_fails_when_a_different_group_is_tampered(tmp_path):
    from faceproof.verify import verify_bundle_locally

    bundle, proofs = assemble_bundle(tmp_path, _stage1(), _stage2())
    bundle["groups"]["scores"]["cosine"] = q(0.123456)   # not match_location
    res = verify_bundle_locally(bundle, proofs)
    assert res["root_match"] is False
    assert res["selective_disclosure_pass"] is False


# --------------------------------------------------------------------------- #
# #2 - proof length is pinned to the tree depth
# --------------------------------------------------------------------------- #

def test_merkle_verify_rejects_wrong_length_proof(tmp_path):
    groups = assemble_groups(_stage1(), _stage2())
    leaves = canonical_leaves(groups)
    layers = build(leaves)
    r = merkle_root(layers)

    assert TREE_DEPTH == 3

    # a depth-1 internal node + its sibling recomputes to the root...
    internal = layers[TREE_DEPTH - 1][1]
    sibling = layers[TREE_DEPTH - 1][0]
    assert verify(internal, [sibling], r) is True                  # unpinned: passes
    assert verify(internal, [sibling], r, expected_len=TREE_DEPTH) is False
    # ...and the root itself with an empty path
    assert verify(r, [], r) is True
    assert verify(r, [], r, expected_len=TREE_DEPTH) is False


# --------------------------------------------------------------------------- #
# #3 - a reverted anchor tx is not reported as success
# --------------------------------------------------------------------------- #

def test_anchor_raises_on_reverted_transaction(tmp_path, monkeypatch):
    import faceproof.anchor as anchor_mod

    bundle, _ = assemble_bundle(tmp_path, _stage1(), _stage2())

    monkeypatch.setattr(anchor_mod, "chain_name", lambda: "anvil")
    monkeypatch.setattr(anchor_mod, "registry_address", lambda: "0x" + "11" * 20)
    monkeypatch.setattr(anchor_mod, "private_key", lambda: "0x" + "22" * 32)
    monkeypatch.setattr(anchor_mod, "rpc_url", lambda name: "http://127.0.0.1:8545")

    class _W3:
        def is_connected(self):
            return True

    monkeypatch.setattr(anchor_mod, "get_w3", lambda *a, **k: _W3())
    monkeypatch.setattr(
        anchor_mod, "anchor_root",
        lambda **kw: {
            "status": 0, "tx_hash": "0xdead", "block_number": 1, "gas_used": 21000,
            "anchor_id": 0, "submitter": "0x" + "33" * 20,
            "contract": "0x" + "11" * 20, "chain_id": 31337,
        },
    )

    with pytest.raises(RuntimeError, match="did not succeed"):
        anchor_mod.anchor(tmp_path)
    assert not (tmp_path / "receipt.json").exists()


# --------------------------------------------------------------------------- #
# #4 - consent leaf commits the token digest exactly once
# --------------------------------------------------------------------------- #

def test_consent_group_has_no_duplicate_commitment():
    groups = assemble_groups(_stage1(), _stage2())
    consent = groups["consent"]
    assert consent["commitment"] == "0x" + "ab" * 32
    assert "subject_ref" not in consent
    # the digest appears once in the canonical bytes of the group
    assert canon(consent).decode().count("ab" * 32) == 1


# --------------------------------------------------------------------------- #
# #5 - the bridge abstains instead of emitting a hollow positive match
# --------------------------------------------------------------------------- #

def _seed_handoff(run_dir):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "probe.json").write_text(json.dumps({
        "status": "accepted", "run_id": "t",
        "model_id": "insightface/buffalo_l@w600k_r50",
        "pipeline_version": "faceproof/1.1.0",
        "quality": {"det_score": "0.950000", "blur_var": "70.000000"},
        "consent": {"subject_commitment": "0x" + "ab" * 32},
        "embedding": {"commitment": "0x" + "cd" * 32},
    }))
    (run_dir / "embedding.f32").write_bytes(
        (np.ones(512, dtype="<f4") / np.sqrt(512)).tobytes()
    )


def test_bridge_abstains_when_winning_channel_has_no_record(tmp_path, monkeypatch):
    from faceproof import stage2_bridge as sb

    _seed_handoff(tmp_path)
    # channel A "accepts" but yields no hit; fuse -> SINGLE_CHANNEL_A
    monkeypatch.setattr(
        sb, "_run_channel_a",
        lambda *a, **k: {"accepted": True, "reason": "accepted", "hits": [],
                         "margin": 0.3, "snapshot": {"snapshot_id": "s"}},
    )
    payload = sb.run_stage2(tmp_path)
    assert payload["fusion_outcome"] == "ABSTAIN"
    assert payload["match"] is None
    assert "without_locatable_match" in payload["reason"]


def test_bridge_single_channel_b_uses_b_record(tmp_path, monkeypatch):
    from faceproof import stage2_bridge as sb

    _seed_handoff(tmp_path)
    monkeypatch.setattr(
        sb, "_run_channel_a",
        lambda *a, **k: {"accepted": False, "reason": "below_threshold", "hits": [],
                         "margin": 0.0, "snapshot": {}},
    )
    monkeypatch.setattr(
        sb, "_run_channel_b",
        lambda *a, **k: {
            "accepted": True, "reason": "verified",
            "post_url": "https://bsky.app/profile/b.bsky.social/post/3kB",
            "post_uri": "at://did:plc:b/app.bsky.feed.post/3kB",
            "author_did": "did:plc:b", "author_handle": "b.bsky.social",
            "score": 0.8,
        },
    )
    payload = sb.run_stage2(tmp_path)
    assert payload["fusion_outcome"] == "SINGLE_CHANNEL_B"
    assert payload["match"]["post_url"].endswith("/post/3kB")
    assert payload["match"]["author_did"] == "did:plc:b"


# --------------------------------------------------------------------------- #
# #6 - accept_at is never read as a timestamp
# --------------------------------------------------------------------------- #

def test_accept_at_is_not_used_as_retrieval_timestamp():
    res = normalize(
        {"fusion_outcome": "SINGLE_CHANNEL_A", "accept_at": "0.55",
         "match": {"post_url": "https://x/y", "score": 0.9}},
        source="test",
    )
    assert res["retrieval_timestamp"] != "0.55"
    assert res["match"]["threshold"] == q(0.55) or "0.55" in res["match"]["threshold"]
