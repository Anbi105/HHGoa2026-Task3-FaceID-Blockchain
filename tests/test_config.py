"""Configuration tests."""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

import pytest

from faceproof.config import Config, banner, cfg


class TestDefaults:
    def test_gate_defaults_match_the_guide(self):
        c = Config()
        assert c.min_det_score == 0.62
        assert c.min_face_px == 90
        assert c.min_blur_var == 45.0
        assert c.max_secondary_face_ratio == 0.60

    def test_model_identity_is_pinned(self):
        assert Config().model_id == "insightface/buffalo_l@w600k_r50"

    def test_frozen(self):
        with pytest.raises(Exception):
            Config().min_det_score = 0.9


class TestEnvOverrides:
    def test_float_override(self, monkeypatch):
        monkeypatch.setenv("FACEPROOF_MIN_BLUR_VAR", "12.5")
        assert Config().min_blur_var == 12.5

    def test_int_override(self, monkeypatch):
        monkeypatch.setenv("FACEPROOF_MIN_FACE_PX", "140")
        assert Config().min_face_px == 140

    def test_str_override(self, monkeypatch):
        monkeypatch.setenv("FACEPROOF_CONSENT_SCOPE", "research")
        assert Config().consent_scope == "research"

    def test_path_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FACEPROOF_DATA_DIR", str(tmp_path))
        assert Config().data_dir == tmp_path

    def test_bad_value_fails_loudly(self, monkeypatch):
        """Silently falling back to the default would mean the config on
        screen is not the config in force."""
        monkeypatch.setenv("FACEPROOF_MIN_FACE_PX", "not-a-number")
        with pytest.raises(ValueError):
            Config()


class TestDerivedPaths:
    def test_under_data_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FACEPROOF_DATA_DIR", str(tmp_path))
        c = Config()
        assert c.calib_dir == tmp_path / "calib"
        assert c.calibration_json == tmp_path / "calibration.json"
        assert c.consent_store == tmp_path / "consent" / "store.json"

    def test_run_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FACEPROOF_OUT_DIR", str(tmp_path))
        assert Config().run_dir("abc") == tmp_path / "run-abc"


class TestPublic:
    def test_covers_every_field(self):
        pub = cfg.public()
        for f in fields(cfg):
            assert f.name in pub

    def test_paths_are_strings(self):
        assert isinstance(cfg.public()["data_dir"], str)

    def test_json_serialisable_and_sorted(self):
        data = json.loads(banner())
        assert list(data) == sorted(data)

    def test_masks_secret_fields(self):
        """Stage 3 will add private_key and serpapi_key here.  Exercise the
        masking on a real dataclass field rather than asserting a constant."""
        from dataclasses import dataclass, field

        @dataclass(frozen=True)
        class WithSecrets(Config):
            private_key: str = "0xdeadbeefdeadbeef"
            serpapi_key: str = ""

        pub = WithSecrets().public()
        assert pub["private_key"] == "<set>"     # value never printed
        assert pub["serpapi_key"] == "<unset>"   # absence is visible
        assert "deadbeef" not in json.dumps(pub)

    def test_banner_would_not_leak_a_secret(self):
        import faceproof.config as mod

        assert "private_key" in mod._SECRET_FIELDS
        assert "serpapi_key" in mod._SECRET_FIELDS
