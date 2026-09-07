"""Check photographs against the Stage 1 quality gate before using them.

Adding a person to the corpus runs InsightFace over every image and then fails
late if the photographs are unusable - which wastes minutes and, worse, can
leave a half-built index behind.  This reports the same three measurements the
gate uses, per file, in a second or two.

    python scripts/check_photos.py data/corpus/alice/*.jpg
    python scripts/check_photos.py data/corpus data/probe

Directories are walked recursively.  Nothing is written and no index is
touched; this only reads and measures.

Two different criteria matter, and they are not the same number:

* the **probe** gate (what this prints) - det_score, face size, blur variance
  and the secondary-face check.  A photograph used as the *query* must clear
  all of it.
* the **gallery** criterion - detector confidence only (guide p.20).  A photo
  that fails the probe gate on blur or size can still be indexed as a corpus
  entry; it just cannot be the probe.
"""

from __future__ import annotations

import glob
import sys
from pathlib import Path

SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def expand(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for arg in args:
        p = Path(arg)
        if p.is_dir():
            out += [q for q in sorted(p.rglob("*")) if q.suffix.lower() in SUFFIXES]
        elif any(ch in arg for ch in "*?["):
            out += [Path(m) for m in sorted(glob.glob(arg))]
        elif p.is_file():
            out.append(p)
        else:
            print(f"  ! not found: {arg}")
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2

    from faceproof.config import cfg
    from faceproof.face import encode

    paths = expand(argv)
    if not paths:
        print("no images found")
        return 2

    print(f"\nStage 1 probe gate:  det_score >= {cfg.min_det_score}   "
          f"face >= {cfg.min_face_px}px   blur_var >= {cfg.min_blur_var}   "
          f"secondary <= {cfg.max_secondary_face_ratio}")
    print(f"Gallery criterion :  det_score >= 0.55 only (guide p.20)\n")

    head = f"{'image':<52}{'det':>7}{'px':>7}{'blur':>10}  verdict"
    print(head); print("-" * len(head))

    probe_ok = gallery_ok = 0
    for path in paths:
        probe, rej = encode(path, strict=True)
        m = rej.metrics if rej is not None else probe.metrics()
        det = float(m.get("det_score", 0) or 0)
        px = int(m.get("face_px", 0) or 0)
        blur = float(m.get("blur_var", 0) or 0)

        if rej is None:
            verdict = "OK - usable as PROBE or gallery"
            probe_ok += 1; gallery_ok += 1
        elif det >= 0.55 and px > 0:
            verdict = f"gallery only ({rej})"
            gallery_ok += 1
        else:
            verdict = f"UNUSABLE ({rej})"

        name = str(path)
        if len(name) > 50:
            name = "..." + name[-47:]
        print(f"{name:<52}{det:>7.3f}{px:>7}{blur:>10.1f}  {verdict}")

    n = len(paths)
    print(f"\n  {probe_ok}/{n} usable as a PROBE      (need >= 1: the held-out photo)")
    print(f"  {gallery_ok}/{n} usable in the GALLERY  (need >= 2 per target subject)")
    if probe_ok == 0:
        print("\n  No photograph can serve as the probe. The usual cause is a")
        print("  messaging-app re-encode or an upscaled crop: face size looks fine")
        print("  but blur_var collapses. Use the ORIGINAL camera file - send it to")
        print("  yourself as a Document/'original quality', or copy it over USB.")
        print("  Do NOT lower the gate to make a photograph pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
