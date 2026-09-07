"""Channel A corpus builder - the fetch step Person 2's Stage 2 is missing (S6).

Person 2 owns Stage 2.  Their pipeline is ``ingest_bsky.ingest`` -> ``raw.jsonl``
-> ``index.build`` -> FAISS, but the two ends do not meet: ``ingest_bsky``
records an ``image_url`` while ``index.build`` requires ``record["local_image"]``,
a file already on disk.  Nothing on the ``person2`` branch downloads it.  The
guide's reference ``index.py`` does that fetch inline; Person 2 factored
``build`` to take pre-fetched records and left the fetcher unwritten.

This module supplies exactly that missing step, additively.  It does **not**
reimplement Person 2's work:

* ingestion stays Person 2's ``ingest_bsky.ingest`` (public Bluesky AppView,
  no auth, only the handles you name);
* detection, embedding and FAISS construction stay Person 2's ``index.build``;
* this module only turns ``image_url`` into ``local_image`` and enriches each
  row with the content digests the evidence bundle has slots for.

It also fixes a second reason ``build`` was unreachable: it does
``from .face import probe_image``, a *relative* import that cannot resolve
under the bridge's flat ``_load_by_path``.  Here the vendored tree is loaded as
a genuine package, so Person 2's own imports work unmodified.

Nothing is invented.  Every row traces to a real public post returned by the
Bluesky API for a handle you supplied; an image that will not download is
skipped and counted, never synthesised.

    python -m faceproof.run corpus --handles alice.bsky.social bob.bsky.social
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional, Tuple

from faceproof.config import cfg

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Same candidates the bridge uses, kept in sync deliberately.
_P2_PKG_CANDIDATES = (
    "vendor/stage2/faceproof",
    "person2/files-mentioned-by-the-user-hhgoa/faceproof/faceproof",
)

_P2_PKG_NAME = "_faceproof_person2"
_UA = {"User-Agent": "faceproof/1.1 (HH Goa 2026 Task 3; research demo)"}
_MIN_IMAGE_BYTES = 1024


class CorpusError(RuntimeError):
    """The corpus could not be built from real data."""


# ---------------------------------------------------------------------------
# Load Person 2's tree as a real package (so their relative imports resolve)
# ---------------------------------------------------------------------------


def p2_package_dir() -> Path:
    for rel in _P2_PKG_CANDIDATES:
        cand = _REPO_ROOT / rel
        if (cand / "index.py").exists():
            return cand
    raise CorpusError(
        "Person 2's Stage 2 package was not found; looked in: "
        + ", ".join(_P2_PKG_CANDIDATES)
    )


def load_p2_module(name: str) -> ModuleType:
    """Import ``vendor/stage2/faceproof/<name>.py`` with package semantics.

    The bridge loads single files flat, which is enough for ``fuse`` and
    ``channel_b`` but breaks ``index.build``'s ``from .face import``.  Loading
    the directory as a package under a private name fixes that without
    touching Person 2's source or shadowing this repo's own ``faceproof``.
    """
    pkg_dir = p2_package_dir()
    if _P2_PKG_NAME not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            _P2_PKG_NAME,
            pkg_dir / "__init__.py",
            submodule_search_locations=[str(pkg_dir)],
        )
        if spec is None or spec.loader is None:  # pragma: no cover - defensive
            raise CorpusError(f"cannot load Person 2 package at {pkg_dir}")
        pkg = importlib.util.module_from_spec(spec)
        sys.modules[_P2_PKG_NAME] = pkg
        spec.loader.exec_module(pkg)
    return importlib.import_module(_P2_PKG_NAME + "." + name)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def index_dir() -> Path:
    return cfg.data_dir / "index"


def raw_path() -> Path:
    return index_dir() / "raw.jsonl"


def images_dir() -> Path:
    return index_dir() / "images"


def records_path() -> Path:
    return index_dir() / "records.jsonl"


# ---------------------------------------------------------------------------
# Step 1 - ingest (delegates to Person 2)
# ---------------------------------------------------------------------------


def ingest(handles: List[str]) -> int:
    """Person 2's real seeded Bluesky ingest -> ``data/index/raw.jsonl``."""
    if not handles:
        raise CorpusError("no handles given; ingestion needs consenting handles")
    mod = load_p2_module("ingest_bsky")
    raw_path().parent.mkdir(parents=True, exist_ok=True)
    rows = mod.ingest(handles, output=str(raw_path()))
    return len(rows)


# ---------------------------------------------------------------------------
# Step 2 - the missing fetch
# ---------------------------------------------------------------------------


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _phash(blob: bytes) -> str:
    """Perceptual hash, if imagehash is installed; empty string otherwise."""
    try:
        import io

        import imagehash
        from PIL import Image
    except ImportError:
        return ""
    try:
        return str(imagehash.phash(Image.open(io.BytesIO(blob)).convert("RGB")))
    except Exception:
        return ""


def fetch_images(
    *, limit: Optional[int] = None, timeout: int = 20, log=print
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Download every image named in ``raw.jsonl``; return enriched records.

    Adds to each row the three things downstream needs and Person 2's ingest
    could not know: ``local_image`` (what ``index.build`` requires),
    ``image_sha256`` and ``image_phash`` (evidence-bundle fields), plus
    ``text_sha256`` so the post text never has to travel further.

    Failures are counted and reported, never replaced with placeholder data.
    """
    import requests

    src = raw_path()
    if not src.exists():
        raise CorpusError(
            str(src) + " not found - run the ingest step first "
            "(python -m faceproof.run corpus --handles <consenting handles>)"
        )

    dest = images_dir()
    dest.mkdir(parents=True, exist_ok=True)

    seen = set()
    records: List[Dict[str, Any]] = []
    stats = {"rows": 0, "duplicate": 0, "fetched": 0, "failed": 0, "too_small": 0}

    for line in src.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if limit is not None and len(records) >= limit:
            break
        rec = json.loads(line)
        stats["rows"] += 1

        key = (rec.get("post_uri", ""), rec.get("image_url", ""))
        if key in seen:
            stats["duplicate"] += 1
            continue
        seen.add(key)

        url = rec.get("image_url")
        if not url:
            stats["failed"] += 1
            continue

        blob = None
        response = None
        try:
            # Keep connection setup and response reads bounded separately.
            # A CDN 504 is then one failed row, not a stalled corpus run.
            response = requests.get(
                url, timeout=(5, timeout), headers=_UA, stream=True
            )
            resp = response
            if resp.ok:
                if hasattr(resp, "iter_content"):
                    deadline = time.monotonic() + timeout
                    chunks = []
                    for chunk in resp.iter_content(64 * 1024):
                        if time.monotonic() > deadline:
                            raise TimeoutError("image download exceeded its deadline")
                        if chunk:
                            chunks.append(chunk)
                    blob = b"".join(chunks)
                else:  # lightweight response doubles used by unit tests
                    blob = resp.content
            else:
                log("  fetch failed: HTTP " + str(resp.status_code) + " " + url[:70])
        except Exception as exc:
            log("  fetch failed: " + type(exc).__name__ + " " + url[:70])
        finally:
            close = getattr(response, "close", None)
            if close is not None:
                close()

        if not blob:
            stats["failed"] += 1
            continue
        if len(blob) < _MIN_IMAGE_BYTES:
            stats["too_small"] += 1
            continue

        digest = _sha256(blob)
        path = dest / (digest[:16] + ".jpg")
        if not path.exists():
            path.write_bytes(blob)

        enriched = dict(rec)
        enriched["local_image"] = str(path)
        enriched["image_sha256"] = digest
        enriched["image_phash"] = _phash(blob)
        enriched["text_sha256"] = _sha256(rec.get("text", "").encode("utf-8"))
        records.append(enriched)
        stats["fetched"] += 1

    records_path().write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in records),
        encoding="utf-8",
    )
    return records, stats


# ---------------------------------------------------------------------------
# Step 3 - build (delegates to Person 2)
# ---------------------------------------------------------------------------


def build_index(records: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Person 2's real ``index.build`` over fetched records -> FAISS + snapshot."""
    if records is None:
        src = records_path()
        if not src.exists():
            raise CorpusError(str(src) + " not found - run the fetch step first")
        records = [
            json.loads(x)
            for x in src.read_text(encoding="utf-8").splitlines()
            if x.strip()
        ]
    if not records:
        raise CorpusError("no fetched records - nothing to index")

    index_mod = load_p2_module("index")
    return index_mod.build(records, cfg, out_dir=str(index_dir()))
