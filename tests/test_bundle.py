"""Stage 3 — eight-group evidence bundle assembly and root recomputation (§7, §8)."""

import json

import pytest

from faceproof.bundle import (
    ABSTAIN_FILENAME,
    BUNDLE_FILENAME,
    GROUPS,
    PROOFS_FILENAME,
    AbstainError,
    assemble_bundle,
    assemble_groups,
    build_bundle,
    build_proofs,
    canonical_leaves,
    compute_root,
    recompute_root,
    verify_bundle_privacy,
    write_abstain,
)
from faceproof.canonical import canon, q
from faceproof.merkle import unhex, verify
from faceproof.stage2_adapter import normalize

PROBE_COMMITMENT = "0x" + "b6" * 32
SUBJECT_COMMITMENT = "0x" + "22" * 32


def stage1_record(status="accepted"):
    return {
        "status": status,
        "model_id": "insightface/buffalo_l@w600k_r50",
        "quality": {"det_score": q(0.96), "blur_var": q(72.5)},
        "consent": {
            "subject_commitment": SUBJECT_COMMITMENT,
            "granted_at": "2026-09-06T06:29:14Z",
            "scope": "face_probe_demo",
        },
        "embedding": {"commitment": PROBE_COMMITMENT},
    }


def stage2_result(outcome="SINGLE_CHANNEL_A"):
    raw = {
        "fusion_outcome": outcome,
        "snapshot_id": "snap-123",
        "margin": 0.14,
        "match": {
            "platform": "bluesky",
            "post_url": "https://bsky.app/profile/alice.bsky.social/post/3kabc",
            "post_uri": "at://did:plc:alice/app.bsky.feed.post/3kabc",
            "author_did": "did:plc:alice",
            "author_handle": "alice.bsky.social",
            "text": "A great day at the beach!",
            "image_sha256": "aa" * 32,
            "phash": "d8e0f0f0",
            "score": 0.79,
        },
    }
    return normalize(raw, source="test")


def test_groups_are_exactly_the_eight_in_order():
    groups = assemble_groups(stage1_record(), stage2_result())
    assert tuple(groups) == GROUPS
    bundle = build_bundle(groups)
    assert bundle["group_order"] == list(GROUPS)
    assert tuple(bundle["groups"]) == GROUPS


def test_probe_and_consent_are_verbatim_from_stage1():
    groups = assemble_groups(stage1_record(), stage2_result())
    # the salted commitment is consumed, never recomputed, never a fresh salt
    assert groups["probe"]["commitment"] == PROBE_COMMITMENT
    assert groups["consent"]["commitment"] == SUBJECT_COMMITMENT
    assert groups["consent"]["subject_ref"] == SUBJECT_COMMITMENT
    # no raw biometric material anywhere
    blob = canon(groups).decode()
    assert "embedding" not in blob and "salt" not in blob


def test_match_text_has_hash_not_text():
    groups = assemble_groups(stage1_record(), stage2_result())
    assert groups["match_text"]["length"] == len("A great day at the beach!")
    assert "beach" not in canon(groups).decode()


def test_missing_or_extra_group_rejected():
    groups = assemble_groups(stage1_record(), stage2_result())
    broken = dict(groups)
    del broken["scores"]
    with pytest.raises(ValueError, match="exactly the 8 groups"):
        compute_root(broken)
    broken2 = dict(groups)
    broken2["surprise"] = {"x": "1"}
    with pytest.raises(ValueError, match="exactly the 8 groups"):
        compute_root(broken2)


def test_raw_float_rejected():
    groups = assemble_groups(stage1_record(), stage2_result())
    groups["scores"]["cosine"] = 0.79  # raw float
    with pytest.raises(TypeError, match="raw float"):
        build_bundle(groups)


def test_recompute_root_ignores_stored_value():
    groups = assemble_groups(stage1_record(), stage2_result())
    bundle = build_bundle(groups)
    true_root = bundle["merkle_root"]
    bundle["merkle_root"] = "0x" + "ff" * 32
    assert recompute_root(bundle) == true_root


def test_proofs_verify_against_recomputed_root():
    groups = assemble_groups(stage1_record(), stage2_result())
    bundle = build_bundle(groups)
    proofs = build_proofs(groups)
    r = unhex(recompute_root(bundle))
    leaves = canonical_leaves(groups)
    assert len(proofs["groups"]) == 8
    for i, name in enumerate(GROUPS):
        entry = proofs["groups"][name]
        assert entry["index"] == i
        assert unhex(entry["leaf"]) == leaves[i]
        assert verify(leaves[i], [unhex(p) for p in entry["proof"]], r)


def test_privacy_guard_catches_leaked_embedding():
    groups = assemble_groups(stage1_record(), stage2_result())
    bundle = build_bundle(groups)
    verify_bundle_privacy(bundle)  # clean bundle passes
    bundle["groups"]["probe"]["embedding"] = [0, 1] * 40
    with pytest.raises(ValueError):
        verify_bundle_privacy(bundle)


def test_abstain_refuses_to_build(tmp_path):
    with pytest.raises(AbstainError):
        assemble_groups(stage1_record(), stage2_result(outcome="ABSTAIN"))
    with pytest.raises(AbstainError):
        assemble_bundle(tmp_path, stage1_record(), stage2_result(outcome="ABSTAIN"))
    assert not (tmp_path / BUNDLE_FILENAME).exists()


def test_assemble_writes_canonical_files(tmp_path):
    bundle, proofs = assemble_bundle(tmp_path, stage1_record(), stage2_result())
    raw = (tmp_path / BUNDLE_FILENAME).read_bytes()
    assert raw == canon(json.loads(raw))  # on-disk form is itself canonical
    assert (tmp_path / PROOFS_FILENAME).exists()
    assert recompute_root(tmp_path / BUNDLE_FILENAME) == bundle["merkle_root"]
    assert proofs["merkle_root"] == bundle["merkle_root"]


def test_write_abstain_marker(tmp_path):
    rec = write_abstain(tmp_path, stage1_record("rejected"), {"fusion_outcome": "ABSTAIN", "source": "x"})
    assert rec["status"] == "ABSTAIN"
    assert (tmp_path / ABSTAIN_FILENAME).exists()
