"""Channel A corpus builder - the fetch step that closes Person 2's gap (S6).

Person 2's ``ingest_bsky`` emits ``image_url``; their ``index.build`` needs
``local_image``.  These tests pin the glue that joins them, and pin that the
glue refuses to invent anything when the real inputs are absent.

No network: the fetch is exercised with a monkeypatched ``requests.get`` that
returns the repository's own committed demo image.  The index build uses that
same fixture, so nothing here stands in for a real social-media corpus.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from faceproof import stage2_corpus as sc

DEMO_IMAGE = Path(__file__).resolve().parent.parent / "data" / "demo" / "synthetic_face.jpg"


# --------------------------------------------------------------------------- #
# Person 2's package must load with package semantics
# --------------------------------------------------------------------------- #

def test_person2_package_loads_with_relative_imports():
    """``index.build`` does ``from .face import`` - a flat loader breaks it."""
    index_mod = sc.load_p2_module("index")
    assert hasattr(index_mod, "build") and hasattr(index_mod, "search")
    # the relative import target must resolve as a submodule of the same package
    face_mod = sc.load_p2_module("face")
    assert face_mod.__name__.endswith(".face")
    assert face_mod.__name__.split(".")[0] == index_mod.__name__.split(".")[0]


def test_missing_person2_package_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "_REPO_ROOT", tmp_path)
    with pytest.raises(sc.CorpusError, match="was not found"):
        sc.p2_package_dir()


# --------------------------------------------------------------------------- #
# The fetch step refuses to invent data
# --------------------------------------------------------------------------- #

def test_fetch_without_raw_jsonl_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "index_dir", lambda: tmp_path)
    with pytest.raises(sc.CorpusError, match="run the ingest step first"):
        sc.fetch_images()


def test_ingest_without_handles_refuses(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "index_dir", lambda: tmp_path)
    with pytest.raises(sc.CorpusError, match="consenting handles"):
        sc.ingest([])


def test_build_without_records_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "index_dir", lambda: tmp_path)
    with pytest.raises(sc.CorpusError, match="nothing to index"):
        sc.build_index([])


# --------------------------------------------------------------------------- #
# The fetch step enriches rows with exactly what downstream needs
# --------------------------------------------------------------------------- #

class _Resp:
    def __init__(self, content, ok=True, status_code=200):
        self.content, self.ok, self.status_code = content, ok, status_code


def _seed_raw(tmp_path, rows):
    (tmp_path / "raw.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )


def test_fetch_adds_local_image_and_digests(tmp_path, monkeypatch):
    blob = DEMO_IMAGE.read_bytes()
    monkeypatch.setattr(sc, "index_dir", lambda: tmp_path)
    monkeypatch.setattr("requests.get", lambda url, **kw: _Resp(blob))

    _seed_raw(tmp_path, [{
        "post_uri": "at://did:plc:x/app.bsky.feed.post/1",
        "post_url": "https://bsky.app/profile/x/post/1",
        "author_did": "did:plc:x", "author_handle": "x.bsky.social",
        "text": "hello", "image_url": "https://cdn.example/a.jpg",
    }])

    records, stats = sc.fetch_images(log=lambda *a, **k: None)
    assert stats["fetched"] == 1 and stats["failed"] == 0
    rec = records[0]
    # the field index.build actually requires
    assert Path(rec["local_image"]).exists()
    # evidence-bundle fields Person 2's ingest could not know
    assert rec["image_sha256"] == hashlib.sha256(blob).hexdigest()
    assert rec["text_sha256"] == hashlib.sha256(b"hello").hexdigest()
    # provenance from the real post is carried through untouched
    assert rec["post_url"] == "https://bsky.app/profile/x/post/1"
    assert rec["author_did"] == "did:plc:x"
    # and it is persisted for a later --skip-ingest rebuild
    assert (tmp_path / "records.jsonl").exists()


def test_fetch_deduplicates_and_counts_failures(tmp_path, monkeypatch):
    blob = DEMO_IMAGE.read_bytes()
    monkeypatch.setattr(sc, "index_dir", lambda: tmp_path)

    calls = {"n": 0}

    def fake_get(url, **kw):
        calls["n"] += 1
        if "bad" in url:
            return _Resp(b"", ok=False, status_code=404)
        if "tiny" in url:
            return _Resp(b"x" * 10)
        return _Resp(blob)

    monkeypatch.setattr("requests.get", fake_get)

    row = lambda uri, url: {
        "post_uri": uri, "post_url": "p", "author_did": "d",
        "author_handle": "h", "text": "", "image_url": url,
    }
    _seed_raw(tmp_path, [
        row("at://1", "https://cdn/ok.jpg"),
        row("at://1", "https://cdn/ok.jpg"),      # exact duplicate
        row("at://2", "https://cdn/bad.jpg"),     # HTTP failure
        row("at://3", "https://cdn/tiny.jpg"),    # too small to be an image
    ])

    records, stats = sc.fetch_images(log=lambda *a, **k: None)
    assert stats == {"rows": 4, "duplicate": 1, "fetched": 1,
                     "failed": 1, "too_small": 1}
    assert len(records) == 1


def test_fetch_respects_limit(tmp_path, monkeypatch):
    blob = DEMO_IMAGE.read_bytes()
    monkeypatch.setattr(sc, "index_dir", lambda: tmp_path)
    monkeypatch.setattr("requests.get", lambda url, **kw: _Resp(blob))
    _seed_raw(tmp_path, [
        {"post_uri": f"at://{i}", "post_url": "p", "author_did": "d",
         "author_handle": "h", "text": "", "image_url": f"https://cdn/{i}.jpg"}
        for i in range(5)
    ])
    records, _ = sc.fetch_images(limit=2, log=lambda *a, **k: None)
    assert len(records) == 2


# --------------------------------------------------------------------------- #
# End to end: Person 2's real build + search over a fetched record
# --------------------------------------------------------------------------- #

@pytest.mark.slow
def test_build_and_search_round_trip(tmp_path, monkeypatch):
    """Proves the closed gap: fetched record -> Person 2's FAISS -> a real hit.

    Uses the repo's own demo image, so this is a plumbing proof and not a
    stand-in for a genuine social-media corpus.
    """
    pytest.importorskip("insightface")
    pytest.importorskip("faiss")

    blob = DEMO_IMAGE.read_bytes()
    monkeypatch.setattr(sc, "index_dir", lambda: tmp_path)
    monkeypatch.setattr("requests.get", lambda url, **kw: _Resp(blob))
    _seed_raw(tmp_path, [{
        "post_uri": "at://did:plc:demo/app.bsky.feed.post/1",
        "post_url": "https://bsky.app/profile/demo/post/1",
        "author_did": "did:plc:demo", "author_handle": "demo",
        "text": "fixture", "image_url": "https://cdn.example/a.jpg",
    }])

    records, _ = sc.fetch_images(log=lambda *a, **k: None)
    summary = sc.build_index(records)

    assert summary["n_faces"] >= 1
    assert len(summary["snapshot_id"]) == 64          # sha256 of the sidecar
    for name in ("faiss.bin", "sidecar.jsonl", "snapshot.json"):
        assert (tmp_path / name).exists()

    # query it back with the same face through Person 2's own search
    from faceproof.config import cfg

    face = sc.load_p2_module("face")
    index = sc.load_p2_module("index")
    emb = face.probe_image(records[0]["local_image"], cfg).embedding
    res = index.search(emb, cfg, out_dir=str(tmp_path))
    assert res["hits"], "a self-query must return the indexed face"
    assert res["hits"][0]["score"] > 0.9
