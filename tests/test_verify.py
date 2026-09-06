"""Stage 3 — independent re-verification, selective disclosure, tamper (§21-23)."""

import json

import pytest

from faceproof.bundle import BUNDLE_FILENAME, assemble_bundle
from faceproof.canonical import canon, q
from faceproof.stage2_adapter import normalize
from faceproof.verify import tamper_demonstration, verify_bundle_locally, verify_run


def _stage1():
    return {
        "status": "accepted",
        "model_id": "insightface/buffalo_l@w600k_r50",
        "quality": {"det_score": q(0.91), "blur_var": q(58.0)},
        "consent": {
            "subject_commitment": "0x" + "11" * 32,
            "granted_at": "2026-09-06T10:00:00Z",
            "scope": "face_probe_demo",
        },
        "embedding": {"commitment": "0x" + "33" * 32},
    }


def _stage2():
    return normalize(
        {
            "fusion_outcome": "CORROBORATED",
            "snapshot_id": "snap-001",
            "margin": 0.15,
            "match": {
                "platform": "bluesky",
                "post_url": "https://bsky.app/profile/alice.bsky.social/post/3k12345",
                "post_uri": "at://did:plc:alice/app.bsky.feed.post/3k12345",
                "author_did": "did:plc:alice",
                "author_handle": "alice.bsky.social",
                "text": "post content",
                "image_sha256": "55" * 32,
                "phash": "12345678",
                "score": 0.81,
            },
        },
        source="test",
    )


@pytest.fixture
def run_dir(tmp_path):
    assemble_bundle(tmp_path, _stage1(), _stage2())
    return tmp_path


def test_local_verification_passes(run_dir):
    bundle = json.loads((run_dir / "bundle.json").read_text())
    proofs = json.loads((run_dir / "proofs.json").read_text())
    res = verify_bundle_locally(bundle, proofs)
    assert res["root_match"] is True
    assert res["selective_disclosure_regenerated"] is True
    assert res["selective_disclosure_stored_proof"] is True
    assert res["selective_disclosure_pass"] is True


def test_verify_run_passes_without_chain(run_dir):
    assert verify_run(run_dir, check_chain=False) is True


def test_recompute_ignores_a_forged_stored_root(run_dir):
    bundle = json.loads((run_dir / "bundle.json").read_text())
    bundle["merkle_root"] = "0x" + "ab" * 32
    (run_dir / "bundle.json").write_bytes(canon(bundle))
    # stored root now a lie -> verification must fail (it recomputes)
    assert verify_run(run_dir, check_chain=False) is False


def test_tamper_one_character_breaks_verification(run_dir):
    orig_ok, detected = tamper_demonstration(run_dir)
    assert orig_ok is True
    assert detected is True


def test_verify_run_missing_bundle_returns_false(tmp_path):
    assert verify_run(tmp_path, check_chain=False) is False


def test_verify_bundle_locally_rejects_wrong_group_count(run_dir):
    bundle = json.loads((run_dir / "bundle.json").read_text())
    bundle["groups"].pop("scores")
    with pytest.raises(ValueError, match="exactly the 8 groups"):
        verify_bundle_locally(bundle)


def test_manual_single_char_edit_fails(run_dir):
    bundle = json.loads((run_dir / "bundle.json").read_text())
    url = bundle["groups"]["match_location"]["post_url"]
    bundle["groups"]["match_location"]["post_url"] = url[:-1] + ("z" if url[-1] != "z" else "y")
    (run_dir / BUNDLE_FILENAME).write_bytes(canon(bundle))
    assert verify_run(run_dir, check_chain=False) is False
