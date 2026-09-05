"""CLI tests — the demo surface, and the consent gate in particular."""

from __future__ import annotations

import json
from unittest.mock import patch

import numpy as np
import pytest

from conftest import make_face
from faceproof.cli import (
    EXIT_NO_CONSENT,
    EXIT_OK,
    EXIT_REJECTED,
    EXIT_USAGE,
    main,
)
from faceproof.config import cfg
from faceproof.consent import ConsentStore, check
from faceproof.handoff import load_record


@pytest.fixture
def image(tmp_path):
    p = tmp_path / "photo.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0 stand-in")
    return p


@pytest.fixture
def detects_one_face():
    """Patch the detector so the CLI runs without the model."""
    with patch("faceproof.face.cv2") as cv2m, patch("faceproof.face.app") as appm, patch(
        "faceproof.face._blur_var", return_value=218.0
    ):
        cv2m.imread.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
        appm.return_value.get.return_value = [make_face(seed=5)]
        yield appm


@pytest.fixture
def detects_blurry():
    with patch("faceproof.face.cv2") as cv2m, patch("faceproof.face.app") as appm, patch(
        "faceproof.face._blur_var", return_value=3.9
    ):
        cv2m.imread.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
        appm.return_value.get.return_value = [make_face(det_score=0.80)]
        yield appm


def _grant(subject="alice"):
    return ConsentStore().grant(subject)


# ---------------------------------------------------------------------------
# The consent gate
# ---------------------------------------------------------------------------


class TestConsentGate:
    def test_probe_without_consent_is_refused(self, image, detects_one_face):
        rc = main(["probe", str(image), "--subject", "stranger"])
        assert rc == EXIT_NO_CONSENT

    def test_refusal_happens_before_detection(self, image, detects_one_face):
        """No face is detected, encoded, or stored for a non-consenting subject."""
        main(["probe", str(image), "--subject", "stranger"])
        detects_one_face.return_value.get.assert_not_called()

    def test_refusal_writes_no_embedding(self, image, detects_one_face):
        main(["probe", str(image), "--subject", "stranger"])
        assert not list(cfg.out_dir.rglob("embedding.f32"))

    def test_revoked_subject_is_refused(self, image, detects_one_face):
        store = ConsentStore()
        store.grant("alice")
        store.revoke("alice")
        assert main(["probe", str(image), "--subject", "alice"]) == EXIT_NO_CONSENT

    def test_expired_consent_is_refused(self, image, detects_one_face):
        store = ConsentStore()
        store.grant("alice", ttl_days=-1)
        assert main(["probe", str(image), "--subject", "alice"]) == EXIT_NO_CONSENT

    def test_consent_allows_the_probe(self, image, detects_one_face):
        _grant("alice")
        assert main(["probe", str(image), "--subject", "alice"]) == EXIT_OK

    def test_subject_is_required(self, image):
        with pytest.raises(SystemExit):
            main(["probe", str(image)])


# ---------------------------------------------------------------------------
# Accepted probe
# ---------------------------------------------------------------------------


class TestProbeAccepted:
    def test_writes_the_full_run_directory(self, image, detects_one_face):
        _grant()
        main(["probe", str(image), "--subject", "alice", "--run-id", "r1"])
        run_dir = cfg.run_dir("r1")
        assert (run_dir / "probe.json").exists()
        assert (run_dir / "embedding.f32").exists()
        assert (run_dir / "manifest.jsonl").exists()

    def test_handoff_record_is_accepted(self, image, detects_one_face):
        _grant()
        main(["probe", str(image), "--subject", "alice", "--run-id", "r1"])
        rec = load_record(cfg.run_dir("r1"))
        assert rec["status"] == "accepted"
        assert rec["embedding"]["commitment"].startswith("0x")
        assert rec["consent"]["subject_commitment"].startswith("0x")

    def test_embedding_digest_matches_the_file(self, image, detects_one_face):
        from faceproof.manifest import sha256_file

        _grant()
        main(["probe", str(image), "--subject", "alice", "--run-id", "r1"])
        rec = load_record(cfg.run_dir("r1"))
        assert rec["embedding"]["sha256"] == sha256_file(
            cfg.run_dir("r1") / "embedding.f32"
        )

    def test_manifest_tells_the_story(self, image, detects_one_face):
        _grant()
        main(["probe", str(image), "--subject", "alice", "--run-id", "r1"])
        events = [
            json.loads(l)["event"]
            for l in (cfg.run_dir("r1") / "manifest.jsonl").read_text().splitlines()
        ]
        for expected in ("run_start", "consent_ok", "quality_gate", "encoded", "run_end"):
            assert expected in events

    def test_manifest_leaks_no_secrets(self, image, detects_one_face):
        rec = _grant()
        main(["probe", str(image), "--subject", "alice", "--run-id", "r1"])
        text = (cfg.run_dir("r1") / "manifest.jsonl").read_text()
        assert rec.token not in text
        assert rec.salt_hex not in text

    def test_run_ids_do_not_collide(self, image, detects_one_face):
        _grant()
        main(["probe", str(image), "--subject", "alice"])
        main(["probe", str(image), "--subject", "alice"])
        assert len(list(cfg.out_dir.glob("run-*"))) == 2


# ---------------------------------------------------------------------------
# Rejected probe
# ---------------------------------------------------------------------------


class TestProbeRejected:
    def test_exit_code_and_record(self, image, detects_blurry):
        _grant()
        rc = main(["probe", str(image), "--subject", "alice", "--run-id", "r2"])
        assert rc == EXIT_REJECTED
        rec = load_record(cfg.run_dir("r2"))
        assert rec["status"] == "rejected"
        assert rec["rejection_reason"].startswith("image_too_blurry")

    def test_abstain_writes_no_embedding(self, image, detects_blurry):
        _grant()
        main(["probe", str(image), "--subject", "alice", "--run-id", "r2"])
        assert not (cfg.run_dir("r2") / "embedding.f32").exists()

    def test_detector_runs_only_once(self, image, detects_blurry):
        """The rejection display must reuse the metrics encode() measured,
        not re-run detection."""
        _grant()
        main(["probe", str(image), "--subject", "alice", "--run-id", "r2"])
        assert detects_blurry.return_value.get.call_count == 1

    def test_unreadable_image(self, tmp_path, detects_one_face):
        _grant()
        with patch("faceproof.face.cv2") as cv2m:
            cv2m.imread.return_value = None
            rc = main(["probe", str(tmp_path / "absent.jpg"), "--subject", "alice"])
        assert rc == EXIT_REJECTED


# ---------------------------------------------------------------------------
# consent subcommands
# ---------------------------------------------------------------------------


class TestConsentCommands:
    def test_grant_then_list(self, capsys):
        assert main(["consent", "grant", "alice"]) == EXIT_OK
        assert main(["consent", "list"]) == EXIT_OK
        assert "alice" in capsys.readouterr().out

    def test_grant_persists_to_the_store(self):
        main(["consent", "grant", "alice"])
        assert check(ConsentStore().get("alice"))[0]

    def test_grant_never_prints_secrets(self, capsys):
        main(["consent", "grant", "alice"])
        out = capsys.readouterr().out
        rec = ConsentStore().get("alice")
        assert rec.token not in out
        assert rec.salt_hex not in out

    def test_revoke(self, capsys):
        main(["consent", "grant", "alice"])
        assert main(["consent", "revoke", "alice"]) == EXIT_OK
        assert ConsentStore().get("alice").salt is None

    def test_revoke_unknown(self):
        assert main(["consent", "revoke", "nobody"]) == EXIT_USAGE

    def test_list_when_empty(self, capsys):
        assert main(["consent", "list"]) == EXIT_OK
        assert "No consent records" in capsys.readouterr().out

    def test_custom_scope_blocks_default_probe(self, image, detects_one_face):
        main(["consent", "grant", "alice", "--scope", "something_else"])
        assert main(["probe", str(image), "--subject", "alice"]) == EXIT_NO_CONSENT


# ---------------------------------------------------------------------------
# Other commands
# ---------------------------------------------------------------------------


class TestOtherCommands:
    def test_config_prints_and_hides_nothing_secret(self, capsys):
        assert main(["config"]) == EXIT_OK
        out = capsys.readouterr().out
        assert "min_det_score" in out
        assert "model_id" in out

    def test_no_args_is_usage_error(self, capsys):
        assert main([]) == EXIT_USAGE

    def test_unknown_command(self):
        with pytest.raises(SystemExit):
            main(["nonsense"])

    def test_setup_preloads(self):
        with patch("faceproof.cli.preload") as pre:
            assert main(["setup"]) == EXIT_OK
        pre.assert_called_once()

    def test_calibrate_delegates(self):
        with patch("faceproof.calibrate.main", return_value=0) as cal:
            assert main(["calibrate", "some/dir"]) == 0
        cal.assert_called_once_with(["some/dir"])
