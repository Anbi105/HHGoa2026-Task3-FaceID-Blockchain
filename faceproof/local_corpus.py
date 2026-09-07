"""Channel A corpus built from local consenting photographs.

Why this exists
---------------
Channel A searches a self-built face index.  Person 2's index is fed from
public Bluesky posts (``stage2_corpus.ingest`` -> ``fetch_images``), but no
member of this team has a Bluesky account, and the public CDN returned 504s on
the one seeded ingest that did run.  Rather than fabricate accounts or posts --
which would make the "genuine search" claim worthless -- this module feeds the
*same* index from real photographs that the subjects supplied with consent.

What it does NOT do
-------------------
It does not replace any part of the search.  It produces records; everything
downstream is unchanged Person 2 code:

* detection, quality, ArcFace embedding, L2 normalisation .. their ``face.probe_image``
* FAISS ``IndexIDMap2(IndexFlatIP(512))``, sidecar, snapshot .. their ``index.build``
* cosine top-k, runner-up, margin, accept/abstain .............. their ``index.search``
* channel fusion .............................................. their ``fuse.fuse``

There is no filename matching, no image-equality shortcut, no hardcoded
identity and no synthetic embedding anywhere in this file.  A photograph in
which InsightFace finds no face is skipped and counted, never substituted.

Layout
------
    data/corpus/
        <subject>/            one directory per consenting subject
            photo1.jpg
            photo2.jpg

The directory name is the subject label.  Provenance is recorded honestly as
local, never dressed up as a social-media post::

    platform      local-consenting-corpus
    author_did    did:local:<subject>
    post_url      local://corpus/<subject>/<filename>

so a bundle built from this corpus is self-describing: nothing in it claims a
Bluesky origin.

    python -m faceproof.run corpus-local --root data/corpus
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from faceproof.config import cfg
from faceproof.stage2_corpus import (
    CorpusError,
    _phash,
    _sha256,
    index_dir,
    load_p2_module,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

SOURCE_TYPE = "local-consenting-corpus"
PLATFORM = "local-consenting-corpus"

DEFAULT_ROOT = "data/corpus"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _rel(path: Path) -> str:
    """Repo-relative posix path.

    The sidecar is written verbatim into ``sidecar.jsonl`` and is echoed by the
    dashboard, so an absolute path here would leak the operator's home
    directory into an artifact -- the same leak ``config._display_path``
    already guards against for ``probe.json``.
    """
    try:
        return path.resolve().relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _subject_dirs(root: Path) -> List[Path]:
    return sorted((d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")),
                  key=lambda d: d.name)


def _images_in(d: Path) -> List[Path]:
    return sorted((p for p in d.iterdir()
                   if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES),
                  key=lambda p: p.name)


def _record(subject: str, image: Path, blob: bytes) -> Dict[str, Any]:
    """One gallery row.  Every field is either measured or an honest local id."""
    rel = _rel(image)
    ref = f"local://corpus/{subject}/{image.name}"
    return {
        # what Person 2's index.build requires
        "local_image": rel,
        # honest provenance -- clearly not a social post
        "platform": PLATFORM,
        "source_type": SOURCE_TYPE,
        "subject": subject,
        "author_did": f"did:local:{subject}",
        "author_handle": subject,
        "post_url": ref,
        "post_uri": ref,
        "source_url": ref,
        # content digests the evidence bundle has slots for
        "image_sha256": _sha256(blob),
        "image_phash": _phash(blob),
        # there is no post text in a local corpus; recorded as empty, not faked
        "text": "",
        "text_sha256": _sha256(b""),
        "text_length": 0,
    }



# --------------------------------------------------------------------------- #
# gallery admission criterion (guide p.20)
# --------------------------------------------------------------------------- #

#: The guide filters *corpus* faces on detector confidence alone::
#:
#:     for fi, f in enumerate(faces):
#:         if f.det_score < 0.55:
#:             continue
#:
#: The blur / face-size / secondary-face checks belong to the *probe* (guide
#: p.15, Stage 1) - they exist to stop a bad **query** producing a confidently
#: wrong answer, not to curate the gallery.  Person 2's ``index.build`` reuses
#: ``probe_image``, so the strict probe gate was being applied to gallery
#: images too, and a soft or small photograph could never be indexed at all.
#:
#: This is NOT a relaxation of the probe gate.  Stage 1 keeps every threshold
#: unchanged; only admission to the searchable corpus follows the guide.
GALLERY_MIN_DET_SCORE = 0.55


def gallery_config(min_det_score: float = GALLERY_MIN_DET_SCORE):
    """``cfg`` with the guide's gallery admission criterion.

    ``probe_image(path, config)`` reads its thresholds from the config it is
    handed, so this changes what enters the index without modifying Person 2's
    module and without touching the global config Stage 1 uses.
    """
    from dataclasses import replace

    return replace(
        cfg,
        min_det_score=float(min_det_score),
        min_face_px=0,                 # guide applies no size gate to the gallery
        min_blur_var=0.0,              # nor a blur gate
        max_secondary_face_ratio=1e9,  # nor an ambiguity gate
    )


# --------------------------------------------------------------------------- #
# scan
# --------------------------------------------------------------------------- #


def scan(root: Path | str | Sequence[Path | str] = DEFAULT_ROOT, *,
         exclude: Sequence[Path | str] = (),
         subjects: Optional[Sequence[str]] = None,
         log: Callable[..., None] = print) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Walk ``root`` and return (records, stats).  Reads files; detects nothing.

    ``exclude`` holds out specific images -- use it for the probe photograph so
    the positive test is a genuine match against a *different* photo of the
    same person rather than a self-match against the identical file.
    """
    # One root or several.  Consenting photographs are not always all filed in
    # the same tree (calibration subjects in particular live under data/calib),
    # and copying them around to build an index would duplicate biometric data
    # for no reason.
    roots_in = [root] if isinstance(root, (str, Path)) else list(root)
    roots: List[Path] = []
    for r in roots_in:
        rp = Path(r)
        if not rp.is_absolute():
            rp = _REPO_ROOT / rp
        if not rp.is_dir():
            raise CorpusError(
                f"{rp} does not exist. Create it and place real consenting "
                f"photographs as <root>/<subject>/*.jpg -- see "
                f"data/corpus/README.md. Nothing is generated for you."
            )
        roots.append(rp)

    held_out = {Path(p).resolve() for p in exclude}
    dirs: List[Path] = []
    for rp in roots:
        dirs.extend(_subject_dirs(rp))
    dirs.sort(key=lambda d: d.name)
    if subjects:
        wanted = set(subjects)
        dirs = [d for d in dirs if d.name in wanted]
    if not dirs:
        raise CorpusError(
            f"no subject directories under {[str(r) for r in roots]}. "
            f"Expected <root>/<subject>/*.jpg"
        )

    records: List[Dict[str, Any]] = []
    stats = {"subjects": 0, "images": 0, "excluded": 0, "duplicate": 0,
             "unreadable": 0, "by_subject": {}}
    seen: Dict[str, str] = {}

    for d in dirs:
        images = _images_in(d)
        if not images:
            log(f"  {d.name}: no images with suffix {IMAGE_SUFFIXES}")
            continue
        kept = 0
        for img in images:
            if img.resolve() in held_out:
                stats["excluded"] += 1
                log(f"  {d.name}/{img.name}: held out (excluded)")
                continue
            try:
                blob = img.read_bytes()
            except OSError as exc:
                stats["unreadable"] += 1
                log(f"  {d.name}/{img.name}: unreadable ({exc})")
                continue
            digest = _sha256(blob)
            if digest in seen:
                stats["duplicate"] += 1
                log(f"  {d.name}/{img.name}: duplicate of {seen[digest]}, skipped")
                continue
            seen[digest] = f"{d.name}/{img.name}"
            records.append(_record(d.name, img, blob))
            kept += 1
        if kept:
            stats["subjects"] += 1
            stats["by_subject"][d.name] = kept
            stats["images"] += kept

    if not records:
        raise CorpusError(
            f"no usable images under {[str(r) for r in roots]}. Place real "
            f"consenting photographs and try again; nothing is generated."
        )
    return records, stats


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #


def build(root: Path | str | Sequence[Path | str] = DEFAULT_ROOT, *,
          exclude: Sequence[Path | str] = (),
          subjects: Optional[Sequence[str]] = None,
          gallery_det: float = GALLERY_MIN_DET_SCORE,
          log: Callable[..., None] = print) -> Dict[str, Any]:
    """Scan ``root`` then hand the records to Person 2's real ``index.build``.

    Returns their snapshot summary, with the per-subject scan stats attached
    under ``scan`` for reporting.  Images in which no face is detected are
    dropped by *their* builder and show up as a gap between ``images`` and
    ``n_faces``; this function does not paper over that.
    """
    log(f"[corpus-local] scanning {root}")
    records, stats = scan(root, exclude=exclude, subjects=subjects, log=log)
    log(f"[corpus-local] {stats['images']} image(s) across "
        f"{stats['subjects']} subject(s): {stats['by_subject']}")

    # Person 2's build opens record["local_image"] relative to the process cwd.
    # Fail loudly here rather than let their loop swallow every image as an
    # "INDEX skipped" and then raise the misleading "check corpus/network".
    missing = [r["local_image"] for r in records if not Path(r["local_image"]).is_file()]
    if missing:
        raise CorpusError(
            f"{len(missing)} corpus image(s) are not resolvable from the current "
            f"working directory (e.g. {missing[0]}). Run this command from the "
            f"repository root: {_REPO_ROOT}"
        )

    # Persist the records so the build is reproducible without a re-scan.
    # The destination is resolved once and passed explicitly: the helpers in
    # stage2_corpus each call their own ``index_dir()``, so routing through
    # them could write the records to a different directory than the one the
    # index itself is built in.
    out = index_dir()
    out.mkdir(parents=True, exist_ok=True)
    (out / "records.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in records),
        encoding="utf-8",
    )

    gcfg = gallery_config(gallery_det)
    log(f"[corpus-local] detecting + embedding with {cfg.model_id} "
        f"(Person 2 index.build)")
    log(f"[corpus-local] gallery admission: det_score >= {gallery_det} "
        f"(guide p.20); the Stage 1 probe gate is unchanged "
        f"(det >= {cfg.min_det_score}, face >= {cfg.min_face_px}px, "
        f"blur >= {cfg.min_blur_var})")
    # Person 2's builder, unchanged: detection, ArcFace, FAISS, sidecar, snapshot.
    # It raises a bare RuntimeError("no faces indexed - check corpus/network")
    # when every image was skipped, which is misleading for a local corpus:
    # there is no network involved, and the real cause is that each photograph
    # failed the quality gate (it prints an "INDEX skipped:" line per image).
    # Translate it into something the operator can act on, without changing the
    # gate or the decision.
    try:
        summary = load_p2_module("index").build(records, gcfg, out_dir=str(out))
    except RuntimeError as exc:
        if "no faces indexed" not in str(exc):
            raise
        raise CorpusError(
            f"none of the {len(records)} photograph(s) produced a usable face, so "
            f"the index is empty (see the 'INDEX skipped:' line above each). The "
            f"gallery admission in force is det_score >= {gallery_det} (guide "
            f"p.20). Supply photographs in which a face is actually detected - "
            f"do not lower the criterion to make a match appear."
        ) from exc

    summary["scan"] = stats
    summary["source_type"] = SOURCE_TYPE
    summary["gallery_min_det_score"] = float(gallery_det)
    summary["n_subjects"] = len({r["subject"] for r in records})
    skipped = stats["images"] - int(summary.get("n_faces", 0))
    summary["n_images_without_face"] = max(0, skipped)

    log(f"[corpus-local] indexed n_faces={summary['n_faces']} "
        f"n_images={summary['n_images']} n_subjects={summary['n_subjects']} "
        f"snapshot={summary['snapshot_id'][:16]}...")
    if skipped > 0:
        log(f"[corpus-local] {skipped} image(s) produced no usable face and "
            f"were skipped by index.build")
    return summary


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #


def stats() -> Optional[Dict[str, Any]]:
    """Real snapshot + sidecar composition, or None when no index exists."""
    snap_path = index_dir() / "snapshot.json"
    side_path = index_dir() / "sidecar.jsonl"
    if not snap_path.is_file():
        return None
    snap = json.loads(snap_path.read_text(encoding="utf-8"))

    rows: List[Dict[str, Any]] = []
    if side_path.is_file():
        rows = [json.loads(x) for x in side_path.read_text(encoding="utf-8").splitlines()
                if x.strip()]

    subjects: Dict[str, int] = {}
    for r in rows:
        key = r.get("subject") or r.get("author_handle") or "(unknown)"
        subjects[key] = subjects.get(key, 0) + 1

    # Integrity: an index outlives the images it was built from. A failed
    # rebuild leaves the previous faiss.bin/sidecar in place, so index-stats
    # can otherwise report a healthy snapshot for a gallery whose source
    # photographs are gone and whose provenance can no longer be re-checked.
    missing = [r.get("local_image") for r in rows
               if r.get("local_image") and not Path(r["local_image"]).is_file()]
    snap["n_subjects"] = len(subjects)
    snap["subjects"] = subjects
    snap["files_missing"] = len(missing)
    snap["missing_examples"] = missing[:3]
    snap["stale"] = bool(missing)
    snap["source_types"] = sorted({r.get("source_type", "bluesky-public-post") for r in rows})
    snap["dim"] = _index_dim()
    return snap


def _index_dim() -> Optional[int]:
    """Vector dimension read from the FAISS index itself, not assumed."""
    try:
        import faiss

        path = index_dir() / "faiss.bin"
        if not path.is_file():
            return None
        return int(faiss.read_index(str(path)).d)
    except Exception:
        return None


def probe_is_in_index(image_sha256: str) -> Optional[Dict[str, Any]]:
    """The sidecar row whose image is byte-identical to the probe, if any.

    A positive match against the *same file* that was indexed proves nothing
    about recognition, so callers surface this rather than quietly reporting a
    cosine of 1.0 as a successful identification.
    """
    side_path = index_dir() / "sidecar.jsonl"
    if not image_sha256 or not side_path.is_file():
        return None
    for line in side_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("image_sha256") == image_sha256:
            return row
    return None
