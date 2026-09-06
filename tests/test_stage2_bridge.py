"""Stage 2 bridge - runs Person 2's real fuse/channel_b, emits stage2.json (S6).

These tests never build a FAISS index or hit the network.  The no-index path
exercises Person 2's real ``fuse`` (which abstains); the match path stubs only
Channel A's retrieval and still runs Person 2's real ``fuse`` and ``channel_b``.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from faceproof import stage2_bridge as sb
from faceproof.stage2_adapter import load_stage2


def _write_handoff(run_dir, status="accepted"):
    (run_dir / "probe.json").write_text(json.dumps({
        "schema_id": "faceproof.probe.v1",
        "status": status,
        "run_id": "test",
        "model_id": "insightface/buffalo_l@w600k_r50",
        "pipeline_version": "faceproof/1.1.0",
        "quality": {"det_score": "0.960000", "blur_var": "72.500000"},
        "consent": {"subject_commitment": "0x" + "ab" * 32},
        "embedding": {"commitment": "0x" + "cd" * 32},
    }), encoding="utf-8")
    (run_dir / "embedding.f32").write_bytes(
        (np.ones(512, dtype="<f4") / np.sqrt(512)).tobytes()
    )


def test_person2_modules_load_by_path():
    mods = sb.load_person2_modules()
    assert set(mods) == {"fuse", "channel_b", "index"}
    # Person 2's real fusion logic, unchanged
    assert mods["fuse"].fuse({"accepted": True}, {"accepted": False})["outcome"] == "SINGLE_CHANNEL_A"
    assert mods["fuse"].fuse({"accepted": False}, {"accepted": False})["outcome"] == "ABSTAIN"
    assert mods["channel_b"].discover(None, None)["accepted"] is False


def test_no_index_abstains_via_person2_fuse(tmp_path):
    _write_handoff(tmp_path)
    payload = sb.run_stage2(tmp_path)

    assert payload["fusion_outcome"] == "ABSTAIN"
    assert payload["match"] is None
    assert payload["source"] == "person2-bridge"
    assert (tmp_path / "stage2.json").exists()

    # Stage 3's adapter consumes it and sees an abstain
    norm = load_stage2(tmp_path)
    assert norm["fusion_outcome"] == "ABSTAIN"
    assert norm["match"] is None
    assert norm["source"] == "person2-file:stage2.json"


def test_stage1_rejection_short_circuits(tmp_path):
    _write_handoff(tmp_path, status="rejected")
    payload = sb.run_stage2(tmp_path)
    assert payload["fusion_outcome"] == "ABSTAIN"
    assert payload["reason"] == "stage1_rejected"


def test_match_path_runs_real_fuse_and_hashes_text(tmp_path, monkeypatch):
    _write_handoff(tmp_path)

    hit = {
        "post_uri": "at://did:plc:alice/app.bsky.feed.post/3kabc",
        "post_url": "https://bsky.app/profile/alice.bsky.social/post/3kabc",
        "author_did": "did:plc:alice",
        "author_handle": "alice.bsky.social",
        "text": "a real post body that must never be written to disk",
        "image_url": "https://cdn.example/img.jpg",
        "score": 0.83,
    }
    fake_channel_a = {
        "accepted": True, "reason": "accepted", "hits": [hit], "margin": 0.12,
        "snapshot": {"snapshot_id": "snap-test-001", "n_faces": 7},
    }
    monkeypatch.setattr(sb, "_run_channel_a", lambda *a, **k: dict(fake_channel_a))

    payload = sb.run_stage2(tmp_path)

    # Person 2's real fuse: A accepted, B not -> SINGLE_CHANNEL_A
    assert payload["fusion_outcome"] == "SINGLE_CHANNEL_A"
    assert payload["channels_used"] == ["channel_a"]
    assert payload["snapshot_id"] == "snap-test-001"
    assert payload["match"]["author_handle"] == "alice.bsky.social"

    raw = (tmp_path / "stage2.json").read_text(encoding="utf-8")
    assert "a real post body" not in raw          # raw text never persisted
    assert "text_sha256" in raw and "text_length" in raw

    norm = load_stage2(tmp_path)
    assert norm["fusion_outcome"] == "SINGLE_CHANNEL_A"
    assert norm["match"]["post_url"] == hit["post_url"]
    assert norm["match"]["author_did"] == "did:plc:alice"


def test_index_stats_none_without_index(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "_index_dir", lambda: tmp_path / "nope")
    assert sb.index_stats() is None


# --------------------------------------------------------------------------- #
# Channel A plumbing: every degraded path returns a not-accepted result and
# never fabricates hits.  (audit #5 / re-audit robustness)
# --------------------------------------------------------------------------- #

class _FakeIndex:
    """Stands in for Person 2's index module."""

    def __init__(self, result=None, raises=None):
        self._result, self._raises = result, raises

    def search(self, embedding, config, out_dir=None):
        if self._raises:
            raise self._raises
        return self._result


def test_channel_a_without_an_index_does_not_fabricate(monkeypatch):
    monkeypatch.setattr(sb, "_index_present", lambda: False)
    out = sb._run_channel_a(_FakeIndex(), None, log=lambda *a, **k: None)
    assert out["accepted"] is False
    assert out["reason"] == "no_local_index"
    assert out["hits"] == []


def test_channel_a_reports_a_corrupt_index_instead_of_crashing(monkeypatch):
    monkeypatch.setattr(sb, "_index_present", lambda: True)
    idx = _FakeIndex(raises=RuntimeError("faiss.bin truncated"))
    out = sb._run_channel_a(idx, None, log=lambda *a, **k: None)
    assert out["accepted"] is False
    assert out["reason"] == "index_error"
    assert out["hits"] == []


def test_channel_a_surfaces_the_top_hit_fields(monkeypatch):
    monkeypatch.setattr(sb, "_index_present", lambda: True)
    hit = {"post_uri": "at://x/1", "post_url": "https://bsky.app/p/1", "score": 0.9}
    idx = _FakeIndex(result={
        "accepted": True, "reason": "accepted", "hits": [hit],
        "margin": 0.31, "snapshot": {"snapshot_id": "snap-xyz", "n_faces": 12},
    })
    out = sb._run_channel_a(idx, None, log=lambda *a, **k: None)
    assert out["accepted"] is True
    assert out["post_url"] == "https://bsky.app/p/1"   # mirrors channel_a.discover
    assert out["snapshot"]["snapshot_id"] == "snap-xyz"


def test_index_stats_reads_the_snapshot(tmp_path, monkeypatch):
    idx = tmp_path / "index"; idx.mkdir()
    (idx / "snapshot.json").write_text(
        json.dumps({"snapshot_id": "abc", "n_faces": 7}), encoding="utf-8"
    )
    monkeypatch.setattr(sb, "_index_dir", lambda: idx)
    assert sb.index_stats()["n_faces"] == 7


def test_missing_person2_package_is_reported_clearly(monkeypatch, tmp_path):
    monkeypatch.setattr(sb, "_REPO_ROOT", tmp_path)
    with pytest.raises(sb.Stage2Unavailable, match="was not found"):
        sb._p2_pkg_dir()


def test_winner_for_single_channel_b_without_a_record_is_empty():
    assert sb._winner_for("SINGLE_CHANNEL_B", {"hits": []}, {"accepted": True}) == {}


def test_winner_for_single_channel_b_finds_a_nested_record():
    b = {"accepted": True, "b": {"post_url": "https://x/y"}}
    assert sb._winner_for("SINGLE_CHANNEL_B", {"hits": []}, b)["post_url"] == "https://x/y"


def test_channels_used_labels_corroboration():
    assert sb._channels_used("CORROBORATED", {}, {}) == ["channel_a", "channel_b"]
    assert sb._channels_used("SINGLE_CHANNEL_B", {}, {}) == ["channel_b"]
