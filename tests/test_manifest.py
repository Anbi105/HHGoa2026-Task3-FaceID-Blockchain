"""Run-manifest tests."""

from __future__ import annotations

import json
import re

import pytest

from faceproof.manifest import Manifest, new_run_id, sha256_bytes, sha256_file


class TestRunId:
    def test_shape(self):
        assert re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{6}", new_run_id())

    def test_unique(self):
        assert len({new_run_id() for _ in range(50)}) == 50


class TestDigests:
    def test_file_matches_bytes(self, tmp_path):
        p = tmp_path / "x.bin"
        data = b"hello faceproof"
        p.write_bytes(data)
        assert sha256_file(p) == sha256_bytes(data)

    def test_large_file_streams(self, tmp_path):
        p = tmp_path / "big.bin"
        data = b"\x00" * (3 << 20)  # 3 MB, larger than the 1 MB chunk
        p.write_bytes(data)
        assert sha256_file(p) == sha256_bytes(data)


class TestManifest:
    def test_creates_directory_and_file(self, tmp_path):
        m = Manifest(tmp_path / "run-abc", echo=False)
        m.log("probe", "start")
        assert m.path.exists()

    def test_appends_one_line_per_record(self, tmp_path):
        m = Manifest(tmp_path / "run-abc", echo=False)
        for i in range(3):
            m.log("probe", "step", i=i)
        assert len(m.path.read_text().strip().splitlines()) == 3
        assert len(m.records()) == 3

    def test_record_fields(self, tmp_path):
        m = Manifest(tmp_path / "run-abc", run_id="abc", echo=False)
        rec = m.log("probe", "quality_gate", result="PASS", blur_var=218.0)
        assert rec["stage"] == "probe"
        assert rec["event"] == "quality_gate"
        assert rec["run_id"] == "abc"
        assert rec["result"] == "PASS"
        assert "ts" in rec and "elapsed_s" in rec

    def test_run_id_derived_from_dir(self, tmp_path):
        assert Manifest(tmp_path / "run-20260101T000000Z-abc123", echo=False).run_id == (
            "20260101T000000Z-abc123"
        )

    def test_lines_are_valid_json_and_sorted(self, tmp_path):
        m = Manifest(tmp_path / "run-abc", echo=False)
        m.log("probe", "start", z=1, a=2)
        line = m.path.read_text().strip()
        keys = list(json.loads(line))
        assert keys == sorted(keys)

    def test_non_serialisable_values_do_not_crash(self, tmp_path):
        """A Path or a numpy scalar must not take the run down mid-recording."""
        from pathlib import Path

        m = Manifest(tmp_path / "run-abc", echo=False)
        m.log("probe", "artifact", path=Path("/tmp/x"))
        assert m.records()[0]["path"] == "/tmp/x"

    def test_artifact_logs_digest_and_size(self, tmp_path):
        target = tmp_path / "bundle.json"
        target.write_text('{"a":1}')
        m = Manifest(tmp_path / "run-abc", echo=False)
        rec = m.artifact("probe", target)
        assert rec["sha256"] == sha256_file(target)
        assert rec["bytes"] == target.stat().st_size
        assert rec["sha256_short"].endswith("...")

    def test_records_empty_before_first_log(self, tmp_path):
        assert Manifest(tmp_path / "run-abc", echo=False).records() == []

    def test_survives_reopen(self, tmp_path):
        d = tmp_path / "run-abc"
        Manifest(d, echo=False).log("probe", "first")
        Manifest(d, echo=False).log("probe", "second")
        assert [r["event"] for r in Manifest(d, echo=False).records()] == [
            "first",
            "second",
        ]
