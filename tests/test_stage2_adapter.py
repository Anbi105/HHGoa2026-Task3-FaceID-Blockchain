"""Stage 3 — read-only adapter onto Stage 2's discovery/fusion interface."""

import json

import pytest

from faceproof.stage2_adapter import (
    OUTCOMES,
    Stage2ResultMissing,
    load_stage2,
    normalize,
)


def test_normalize_hashes_and_drops_raw_text():
    raw = {
        "fusion_outcome": "SINGLE_CHANNEL_A",
        "hits": [{
            "platform": "bluesky",
            "post_url": "https://bsky.app/p/1",
            "post_uri": "at://did:plc:x/app.bsky.feed.post/1",
            "author_did": "did:plc:x",
            "author_handle": "x.bsky.social",
            "text": "secret post body",
            "image_sha256": "ab" * 32,
            "phash": "1234",
            "score": 0.8,
        }],
        "margin": 0.2,
    }
    out = normalize(raw, source="unit")
    m = out["match"]
    assert "text" not in m and "secret" not in json.dumps(out)
    assert m["text_length"] == len("secret post body")
    assert len(m["text_sha256"]) == 64
    # numbers are fixed-precision strings
    assert m["cosine"] == "0.800000" and m["margin"] == "0.200000"


def test_abstain_has_no_match():
    out = normalize({"fusion_outcome": "ABSTAIN"}, source="unit")
    assert out["fusion_outcome"] == "ABSTAIN"
    assert out["match"] is None


def test_unknown_outcome_becomes_abstain():
    assert normalize({"outcome": "banana"}, source="u")["fusion_outcome"] == "ABSTAIN"


def test_load_prefers_person2_file(tmp_path):
    (tmp_path / "stage2.json").write_text(json.dumps({
        "fusion_outcome": "CORROBORATED",
        "match": {"post_url": "https://x/y", "score": 0.9},
    }))
    out = load_stage2(tmp_path)
    assert out["source"].startswith("person2-file")
    assert out["fusion_outcome"] == "CORROBORATED"


def test_load_without_stage2_file_refuses_by_default(tmp_path):
    """The stub is a positive, anchorable match — reaching it must be a choice.

    Before this was gated, an empty run directory silently produced a
    fabricated `SINGLE_CHANNEL_A` result that Stage 3 would happily bundle
    and anchor.
    """
    with pytest.raises(Stage2ResultMissing) as exc:
        load_stage2(tmp_path)
    assert "--demo" in str(exc.value)


def test_load_falls_back_to_labelled_stub_when_asked(tmp_path):
    out = load_stage2(tmp_path, allow_synthetic=True)
    assert out["source"] == "synthetic-stub"
    assert out["fusion_outcome"] in OUTCOMES
    assert out["match"] is not None
    assert "synthetic" in out["channels_used"][0]
