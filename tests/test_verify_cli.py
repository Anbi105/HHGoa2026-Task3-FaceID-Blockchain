"""The standalone verifier CLI and the lazy package surface (§7, audit #18).

A third party must be able to re-verify a bundle without the face stack.  Two
things make that true and both are pinned here: ``faceproof/__init__.py``
resolves its heavy names lazily, and ``faceproof.verify_cli`` imports only the
crypto core.
"""

from __future__ import annotations

import builtins
import json
import sys

import pytest

from faceproof import verify_cli
from faceproof.bundle import assemble_bundle
from faceproof.canonical import canon, q
from faceproof.stage2_adapter import normalize


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
            "snapshot_id": "snap-cli",
            "margin": 0.2,
            "match": {
                "platform": "bluesky",
                "post_url": "https://bsky.app/profile/a.bsky.social/post/3kcli",
                "post_uri": "at://did:plc:a/app.bsky.feed.post/3kcli",
                "author_did": "did:plc:a",
                "author_handle": "a.bsky.social",
                "text": "cli test",
                "image_sha256": "ef" * 32,
                "phash": "12345678",
                "score": 0.88,
            },
        },
        source="test",
    )


@pytest.fixture
def run_dir(tmp_path):
    assemble_bundle(tmp_path, _stage1(), _stage2())
    return tmp_path


# --------------------------------------------------------------------------- #
# verify_cli
# --------------------------------------------------------------------------- #

class TestVerifyCli:
    def test_help_exits_cleanly(self, capsys):
        with pytest.raises(SystemExit) as exc:
            verify_cli.main(["--help"])
        assert exc.value.code == 0
        assert "re-verify" in capsys.readouterr().out.lower()

    def test_missing_directory_returns_2(self, tmp_path):
        assert verify_cli.main([str(tmp_path / "nope")]) == 2

    def test_intact_bundle_verifies(self, run_dir):
        assert verify_cli.main([str(run_dir)]) == 0

    def test_tampered_bundle_fails(self, run_dir):
        bundle = json.loads((run_dir / "bundle.json").read_text(encoding="utf-8"))
        bundle["groups"]["match_location"]["post_url"] += "x"
        (run_dir / "bundle.json").write_bytes(canon(bundle))
        assert verify_cli.main([str(run_dir)]) == 1

    def test_tamper_flag_runs_the_demonstration(self, run_dir, capsys):
        rc = verify_cli.main([str(run_dir), "--tamper"])
        out = capsys.readouterr().out
        assert "TAMPER DEMONSTRATION" in out
        assert "DETECTED" in out
        assert rc == 0            # original verified AND tampering was caught

    def test_no_argv_requires_a_run_dir(self):
        with pytest.raises(SystemExit):
            verify_cli.main([])


# --------------------------------------------------------------------------- #
# lazy package surface
# --------------------------------------------------------------------------- #

class TestLazyPackage:
    def test_unknown_attribute_still_raises(self):
        import faceproof

        with pytest.raises(AttributeError, match="no attribute 'definitely_not_here'"):
            faceproof.definitely_not_here

    def test_dir_advertises_the_lazy_api(self):
        import faceproof

        names = dir(faceproof)
        for expected in ("encode", "Probe", "ConsentStore", "cosine"):
            assert expected in names

    def test_lazy_names_resolve_to_the_real_objects(self):
        import faceproof
        from faceproof.face import encode as real_encode

        assert faceproof.encode is real_encode

    def test_crypto_core_imports_without_the_face_stack(self):
        """The point of the lazy __init__: a verifier needs no cv2/insightface."""
        blocked = {"cv2", "insightface", "onnxruntime", "faiss"}
        real_import = builtins.__import__

        def guard(name, *a, **k):
            if name.split(".")[0] in blocked:
                raise ImportError(f"No module named {name!r} (simulated)")
            return real_import(name, *a, **k)

        saved = {k: v for k, v in sys.modules.items()
                 if k.split(".")[0] in blocked or k.startswith("faceproof")}
        for k in saved:
            del sys.modules[k]
        builtins.__import__ = guard
        try:
            import faceproof                     # noqa: F401
            import faceproof.canonical           # noqa: F401
            import faceproof.merkle              # noqa: F401
            import faceproof.bundle              # noqa: F401
            import faceproof.verify              # noqa: F401
            import faceproof.verify_cli          # noqa: F401
        finally:
            builtins.__import__ = real_import
            sys.modules.update(saved)
