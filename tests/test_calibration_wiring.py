"""The measured threshold must actually reach the matcher (guide §5, D3).

``calibrate.py`` writes ``data/calibration.json`` and the guide says to cite
``suggested_accept_at`` in the recording -- but nothing read that file, so the
gate kept using the 0.55 placeholder and the number on camera would not be the
number in force.  These tests pin the precedence:

    FACEPROOF_ACCEPT_AT  >  data/calibration.json  >  0.55 placeholder

No calibration data is invented: each case writes a calibration file shaped
like ``calibrate.py``'s own output into a temp dir and reads the value back.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_READ_ACCEPT_AT = "from faceproof.config import cfg; print(cfg.accept_at)"
_REPO = Path(__file__).resolve().parent.parent


def _effective_accept_at(**env: str) -> float:
    """cfg.accept_at as a fresh process sees it (cfg is a module singleton)."""
    child = dict(os.environ)
    child.pop("FACEPROOF_ACCEPT_AT", None)
    child.update(env)
    child["PYTHONIOENCODING"] = "utf-8"
    out = subprocess.run(
        [sys.executable, "-c", _READ_ACCEPT_AT],
        capture_output=True, text=True, env=child, cwd=str(_REPO),
    )
    assert out.returncode == 0, out.stderr
    return float(out.stdout.strip())


def _write_calibration(dirpath: Path, value: float) -> None:
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / "calibration.json").write_text(
        json.dumps({
            "n_subjects": 3,
            "genuine": {"n": 9, "mean": 0.81, "min": 0.72},
            "impostor": {"n": 27, "mean": 0.24, "max": float(value) - 0.03},
            "suggested_accept_at": float(value),
            "true_accept_rate": 0.94,
        }),
        encoding="utf-8",
    )


def test_placeholder_is_used_when_nothing_is_measured(tmp_path):
    assert _effective_accept_at(FACEPROOF_DATA_DIR=str(tmp_path / "empty")) == 0.55


def test_measured_threshold_overrides_the_placeholder(tmp_path):
    _write_calibration(tmp_path, 0.6123)
    assert _effective_accept_at(FACEPROOF_DATA_DIR=str(tmp_path)) == pytest.approx(0.6123)


def test_explicit_env_beats_a_measured_file(tmp_path):
    _write_calibration(tmp_path, 0.6123)
    got = _effective_accept_at(FACEPROOF_DATA_DIR=str(tmp_path),
                               FACEPROOF_ACCEPT_AT="0.71")
    assert got == pytest.approx(0.71)


def test_malformed_calibration_falls_back_instead_of_crashing(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "calibration.json").write_text("{not json", encoding="utf-8")
    assert _effective_accept_at(FACEPROOF_DATA_DIR=str(tmp_path)) == 0.55


def test_calibration_without_the_key_falls_back(tmp_path):
    (tmp_path / "calibration.json").write_text(
        json.dumps({"n_subjects": 2}), encoding="utf-8"
    )
    assert _effective_accept_at(FACEPROOF_DATA_DIR=str(tmp_path)) == 0.55


def test_committed_calibration_is_a_real_measurement():
    """If data/calibration.json exists it must be a genuine calibrate.py output.

    The file is committable by design (the guide asks for it) and it is the
    single strongest artifact that the threshold was measured rather than
    guessed -- so it must never be hand-written.  These checks would fail on a
    fabricated file: the schema, a real dataset fingerprint, the documented
    rule, and internal consistency between the rule and the number in force.
    """
    path = _REPO / "data" / "calibration.json"
    if not path.exists():
        pytest.skip("no calibration measured yet - run: python -m faceproof.calibrate data/calib")

    d = json.loads(path.read_text(encoding="utf-8"))
    assert d["schema"] == "faceproof.calibration.v1"
    assert len(d["dataset"]["fingerprint"]) == 64          # sha256 of the image set
    assert d["dataset"]["n_subjects"] >= 2                 # guide minimum
    assert d["genuine"]["n"] >= 1 and d["impostor"]["n"] >= 1

    # the number in force must follow the documented rule, not an edit
    assert d["rule"] == "accept_at = impostor_max + 0.03"
    assert d["suggested_accept_at"] == pytest.approx(d["impostor"]["max"] + 0.03, abs=5e-4)

    # and the distributions must be self-consistent
    assert d["genuine"]["min"] <= d["genuine"]["mean"] <= d["genuine"]["max"]
    assert d["impostor"]["min"] <= d["impostor"]["mean"] <= d["impostor"]["max"]
    assert d["separation"] == pytest.approx(d["genuine"]["min"] - d["impostor"]["max"], abs=5e-4)


def test_a_measured_calibration_is_the_threshold_in_force():
    """Whatever calibrate.py measured must be what cfg.accept_at reports."""
    path = _REPO / "data" / "calibration.json"
    if not path.exists():
        pytest.skip("no calibration measured yet")
    measured = json.loads(path.read_text(encoding="utf-8"))["suggested_accept_at"]
    assert _effective_accept_at() == pytest.approx(measured)
