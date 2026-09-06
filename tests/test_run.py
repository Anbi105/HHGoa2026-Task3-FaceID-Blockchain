"""Stage 3 — run.py command surface (no network / no Foundry needed)."""

import argparse
import json

import pytest

from faceproof import run as run_mod
from faceproof.bundle import ABSTAIN_FILENAME, BUNDLE_FILENAME, GROUPS, PROOFS_FILENAME
from faceproof.canonical import q


def _ns(**kw):
    base = dict(run_dir=None, img=None, subject="alice", anchor=False, no_tamper=False, chain=False)
    base.update(kw)
    return argparse.Namespace(**base)


def _seed_run(dirpath, *, rejected=False):
    dirpath.mkdir(parents=True, exist_ok=True)
    probe = {
        "status": "rejected" if rejected else "accepted",
        "run_id": dirpath.name.removeprefix("run-"),
        "model_id": "insightface/buffalo_l@w600k_r50",
        "quality": {"det_score": q(0.93), "blur_var": q(60.0)},
        "consent": {
            "subject_commitment": "0x" + "11" * 32,
            "granted_at": "2026-09-06T10:00:00Z",
            "scope": "face_probe_demo",
        },
        "embedding": {"commitment": "0x" + "22" * 32},
    }
    (dirpath / "probe.json").write_text(json.dumps(probe))
    if not rejected:
        (dirpath / "stage2.json").write_text(json.dumps({
            "fusion_outcome": "SINGLE_CHANNEL_A",
            "snapshot_id": "snap-run-test",
            "margin": 0.2,
            "match": {
                "platform": "bluesky",
                "post_url": "https://bsky.app/profile/a.bsky.social/post/3krun",
                "post_uri": "at://did:plc:a/app.bsky.feed.post/3krun",
                "author_did": "did:plc:a",
                "author_handle": "a.bsky.social",
                "text": "run.py test post",
                "image_sha256": "ab" * 32,
                "phash": "1234abcd",
                "score": 0.77,
            },
        }))
    return dirpath


def test_banner(capsys):
    assert run_mod.cmd_banner(_ns()) == 0
    assert "pipeline_version" in capsys.readouterr().out


def test_index_stats_without_snapshot(capsys):
    assert run_mod.cmd_index_stats(_ns()) == 0
    assert "snapshot" in capsys.readouterr().out.lower()


def test_search_builds_bundle_then_verifies_and_tampers(tmp_path):
    run_dir = _seed_run(tmp_path / "run-abc123")
    rc = run_mod.cmd_search(_ns(run_dir=str(run_dir)))
    assert rc == 0
    assert (run_dir / BUNDLE_FILENAME).exists()
    assert (run_dir / PROOFS_FILENAME).exists()
    bundle = json.loads((run_dir / BUNDLE_FILENAME).read_text())
    # bundle.json is canonicalised (keys sorted); group_order is authoritative
    assert bundle["group_order"] == list(GROUPS)
    assert set(bundle["groups"]) == set(GROUPS)


def test_search_on_rejected_probe_abstains(tmp_path):
    run_dir = _seed_run(tmp_path / "run-rej", rejected=True)
    rc = run_mod.cmd_search(_ns(run_dir=str(run_dir)))
    assert rc == 1
    assert (run_dir / ABSTAIN_FILENAME).exists()
    assert not (run_dir / BUNDLE_FILENAME).exists()


def test_verify_and_tamper_commands(tmp_path):
    run_dir = _seed_run(tmp_path / "run-vt")
    assert run_mod.cmd_search(_ns(run_dir=str(run_dir), no_tamper=True)) == 0
    assert run_mod.cmd_verify(_ns(run_dir=str(run_dir))) == 0
    assert run_mod.cmd_tamper(_ns(run_dir=str(run_dir))) == 0


def test_parser_requires_subcommand():
    with pytest.raises(SystemExit):
        run_mod.build_parser().parse_args([])


def test_main_dispatches_banner(capsys):
    assert run_mod.main(["banner"]) == 0
    assert "model_id" in capsys.readouterr().out
