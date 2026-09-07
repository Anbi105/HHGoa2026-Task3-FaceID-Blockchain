"""The local consenting corpus - the Channel A source used for the demo.

No member of the team has a Bluesky account, so the gallery is built from
photographs the subjects supplied with consent instead of from public posts.
These tests pin the two things that matter about that substitution:

* it produces records for Person 2's real ``index.build`` and nothing else --
  no filename matching, no image equality, no fabricated embedding;
* its provenance is recorded honestly as local, so a bundle built from it can
  never be mistaken for evidence retrieved from a social network.

The image fixtures are the repository's own committed demo images, so nothing
here stands in for a real person's photograph.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from faceproof import local_corpus as lc
from faceproof.stage2_corpus import CorpusError

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "data" / "demo" / "synthetic_face.jpg"
NOFACE = REPO / "data" / "demo" / "noface.jpg"


def _corpus(tmp_path: Path, layout: dict[str, list[Path]]) -> Path:
    root = tmp_path / "corpus"
    for subject, images in layout.items():
        d = root / subject
        d.mkdir(parents=True)
        for i, src in enumerate(images, 1):
            (d / f"photo{i}{src.suffix}").write_bytes(src.read_bytes())
    return root


# --------------------------------------------------------------------------- #
# refusing to invent data
# --------------------------------------------------------------------------- #


def test_missing_root_is_an_error(tmp_path):
    with pytest.raises(CorpusError, match="does not exist"):
        lc.scan(tmp_path / "nope")


def test_root_without_subject_directories_is_an_error(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    with pytest.raises(CorpusError, match="no subject directories"):
        lc.scan(root)


def test_subject_directory_without_images_is_an_error(tmp_path):
    root = tmp_path / "corpus"
    (root / "alice").mkdir(parents=True)
    with pytest.raises(CorpusError, match="no usable images"):
        lc.scan(root, log=lambda *a: None)


# --------------------------------------------------------------------------- #
# the records it produces
# --------------------------------------------------------------------------- #


def test_scan_records_carry_what_build_and_the_bundle_need(tmp_path):
    root = _corpus(tmp_path, {"alice": [DEMO]})
    records, stats = lc.scan(root, log=lambda *a: None)

    assert stats["subjects"] == 1 and stats["images"] == 1
    rec = records[0]

    # the one field Person 2's index.build actually requires
    assert rec["local_image"].endswith("photo1.jpg")
    assert Path(rec["local_image"]).is_file()

    # measured, not invented
    assert rec["image_sha256"] == hashlib.sha256(DEMO.read_bytes()).hexdigest()

    # there is no post text in a local corpus; it is empty, not fabricated
    assert rec["text"] == ""
    assert rec["text_sha256"] == hashlib.sha256(b"").hexdigest()
    assert rec["text_length"] == 0


def test_provenance_never_claims_a_social_network(tmp_path):
    root = _corpus(tmp_path, {"alice": [DEMO]})
    records, _ = lc.scan(root, log=lambda *a: None)
    rec = records[0]

    assert rec["platform"] == "local-consenting-corpus"
    assert rec["source_type"] == "local-consenting-corpus"
    assert rec["author_did"] == "did:local:alice"
    assert rec["post_url"].startswith("local://corpus/alice/")
    assert rec["post_uri"] == rec["post_url"]

    # nothing in the row may look like a Bluesky origin
    blob = json.dumps(rec)
    for forbidden in ("bsky", "at://", "did:plc:", "https://"):
        assert forbidden not in blob, f"{forbidden!r} leaked into a local record"


def test_subject_label_comes_from_the_directory_not_the_filename(tmp_path):
    root = _corpus(tmp_path, {"bob": [DEMO]})
    records, _ = lc.scan(root, log=lambda *a: None)
    assert records[0]["subject"] == "bob"
    assert records[0]["author_handle"] == "bob"


# --------------------------------------------------------------------------- #
# holding out the probe
# --------------------------------------------------------------------------- #


def test_exclude_holds_out_the_probe_photograph(tmp_path):
    root = _corpus(tmp_path, {"alice": [DEMO, NOFACE]})
    held = root / "alice" / "photo1.jpg"
    records, stats = lc.scan(root, exclude=[held], log=lambda *a: None)

    assert stats["excluded"] == 1
    assert all(not r["local_image"].endswith("alice/photo1.jpg") for r in records)


def test_identical_images_are_deduplicated(tmp_path):
    root = tmp_path / "corpus"
    (root / "alice").mkdir(parents=True)
    for name in ("a.jpg", "b.jpg"):
        (root / "alice" / name).write_bytes(DEMO.read_bytes())
    records, stats = lc.scan(root, log=lambda *a: None)
    assert stats["duplicate"] == 1
    assert len(records) == 1


def test_subjects_filter_restricts_the_gallery(tmp_path):
    root = _corpus(tmp_path, {"alice": [DEMO], "bob": [NOFACE]})
    records, stats = lc.scan(root, subjects=["alice"], log=lambda *a: None)
    assert {r["subject"] for r in records} == {"alice"}
    assert stats["subjects"] == 1


# --------------------------------------------------------------------------- #
# self-match detection
# --------------------------------------------------------------------------- #


def test_probe_in_index_is_detected_by_digest(tmp_path, monkeypatch):
    monkeypatch.setattr(lc, "index_dir", lambda: tmp_path)
    digest = hashlib.sha256(DEMO.read_bytes()).hexdigest()
    (tmp_path / "sidecar.jsonl").write_text(
        json.dumps({"image_sha256": digest, "subject": "alice",
                    "local_image": "data/corpus/alice/photo1.jpg"}) + "\n",
        encoding="utf-8")

    hit = lc.probe_is_in_index(digest)
    assert hit is not None and hit["subject"] == "alice"
    assert lc.probe_is_in_index("f" * 64) is None
    assert lc.probe_is_in_index("") is None


# --------------------------------------------------------------------------- #
# end to end through Person 2's real builder
# --------------------------------------------------------------------------- #


def test_paths_inside_the_repo_are_recorded_relative(tmp_path):
    """A corpus under the repo must not put an absolute path in the sidecar.

    ``sidecar.jsonl`` is echoed by the dashboard, so an absolute path would
    leak the operator's home directory into an artifact.
    """
    inside = REPO / "data" / "corpus"
    rel = lc._rel(inside / "alice" / "photo1.jpg")
    assert rel == "data/corpus/alice/photo1.jpg"
    assert not Path(rel).is_absolute()


@pytest.mark.slow
def test_build_uses_person2_builder_and_counts_faceless_images(tmp_path, monkeypatch):
    """End to end: real detection, real FAISS - and an honest skip count.

    ``noface.jpg`` contains no face, so Person 2's ``index.build`` drops it.
    The summary must show the gap rather than pad ``n_faces``.
    """
    pytest.importorskip("insightface")
    pytest.importorskip("faiss")

    root = _corpus(tmp_path, {"alice": [DEMO], "nobody": [NOFACE]})
    out = tmp_path / "index"
    monkeypatch.setattr(lc, "index_dir", lambda: out)

    summary = lc.build(root, log=lambda *a: None)

    assert summary["n_faces"] == 1                  # only the real face
    assert summary["scan"]["images"] == 2           # both were offered
    assert summary["n_images_without_face"] == 1    # and the gap is reported
    assert summary["source_type"] == "local-consenting-corpus"
    assert len(summary["snapshot_id"]) == 64
    assert summary["model_id"] == "insightface/buffalo_l@w600k_r50"
    for name in ("faiss.bin", "sidecar.jsonl", "snapshot.json"):
        assert (out / name).is_file()

    # the vector really is a 512-D ArcFace embedding, not a stand-in
    import faiss
    idx = faiss.read_index(str(out / "faiss.bin"))
    assert idx.d == 512 and idx.ntotal == 1
