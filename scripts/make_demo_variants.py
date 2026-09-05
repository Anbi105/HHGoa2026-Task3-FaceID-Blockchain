"""Derive quality-gate demo images from one real consenting photo.

    python scripts/make_demo_variants.py path/to/photo.jpg [--subject alice]

Writes into data/demo/:

    <subject>_ok.jpg       the original, expected to PASS
    <subject>_blurry.jpg   blurred until blur_var < min_blur_var  → image_too_blurry
    <subject>_tiny.jpg     downscaled until side < min_face_px    → face_too_small
    <subject>_crowd.jpg    two comparable faces                   → ambiguous_subject

Each variant is searched for, not guessed: the script increases the blur
(or shrinks the face) step by step and re-runs the real detector until the
image lands in the intended rejection branch, then verifies the branch by
calling encode() and comparing the reason.  If a branch cannot be reached
it says so instead of writing a fixture that does not demonstrate what it
claims.

Use a photo of someone who has consented.  data/demo/ is gitignored apart
from the synthetic fixtures.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from faceproof.config import cfg  # noqa: E402
from faceproof.face import encode  # noqa: E402

OUT = ROOT / "data" / "demo"


def _write(path: Path, img: np.ndarray) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)
    return path


def _reason(path: Path) -> str:
    probe, rejection = encode(path, strict=True)
    return "PASS" if probe is not None else str(rejection)


def make_ok(src: np.ndarray, stem: str) -> tuple[Path, bool]:
    path = _write(OUT / f"{stem}_ok.jpg", src)
    got = _reason(path)
    return path, got == "PASS"


def make_blurry(src: np.ndarray, stem: str) -> tuple[Path, bool]:
    """Find the mildest blur that trips the blur gate while staying detected."""
    for k, sigma in [(9, 3), (15, 6), (21, 9), (31, 13), (41, 18), (51, 25)]:
        img = cv2.GaussianBlur(src, (k, k), sigma)
        path = _write(OUT / f"{stem}_blurry.jpg", img)
        got = _reason(path)
        if got.startswith("image_too_blurry"):
            print(f"      (gaussian k={k} sigma={sigma})")
            return path, True
    return OUT / f"{stem}_blurry.jpg", False


def make_tiny(src: np.ndarray, stem: str) -> tuple[Path, bool]:
    """Shrink the face until it falls under min_face_px but stays detected."""
    h, w = src.shape[:2]
    for scale in [0.45, 0.40, 0.35, 0.30, 0.25, 0.20]:
        small = cv2.resize(src, (int(w * scale), int(h * scale)))
        canvas = np.full((h, w, 3), 210, dtype=np.uint8)
        sh, sw = small.shape[:2]
        y, x = (h - sh) // 2, (w - sw) // 2
        canvas[y:y + sh, x:x + sw] = small
        path = _write(OUT / f"{stem}_tiny.jpg", canvas)
        got = _reason(path)
        if got.startswith("face_too_small"):
            print(f"      (scale={scale})")
            return path, True
    return OUT / f"{stem}_tiny.jpg", False


def make_crowd(src: np.ndarray, stem: str) -> tuple[Path, bool]:
    """Place two comparably-sized faces side by side."""
    mirrored = cv2.flip(src, 1)
    for pad in (0, 40, 80):
        h, w = src.shape[:2]
        canvas = np.full((h, w * 2 + pad, 3), 210, dtype=np.uint8)
        canvas[:, :w] = src
        canvas[:, w + pad:] = mirrored
        path = _write(OUT / f"{stem}_crowd.jpg", canvas)
        got = _reason(path)
        if got.startswith("ambiguous_subject"):
            print(f"      (pad={pad}px)")
            return path, True
    return OUT / f"{stem}_crowd.jpg", False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("photo", help="a photo of a consenting subject")
    ap.add_argument("--subject", default=None, help="filename prefix (default: 'demo')")
    args = ap.parse_args()

    src_path = Path(args.photo)
    src = cv2.imread(str(src_path))
    if src is None:
        print(f"error: cannot read {src_path}", file=sys.stderr)
        return 2

    stem = args.subject or "demo"

    print(f"source: {src_path}  ({src.shape[1]}x{src.shape[0]})")
    print(f"gate:   det>={cfg.min_det_score}  size>={cfg.min_face_px}px  "
          f"blur>={cfg.min_blur_var}  secondary<={cfg.max_secondary_face_ratio}\n")

    builders = [
        ("PASS", make_ok),
        ("image_too_blurry", make_blurry),
        ("face_too_small", make_tiny),
        ("ambiguous_subject", make_crowd),
    ]

    failures = []
    for want, fn in builders:
        path, ok = fn(src, stem)
        got = _reason(path) if path.exists() else "<not written>"
        print(f"  [{'ok ' if ok else 'FAIL'}] {path.name:<24} want={want:<20} got={got}")
        if not ok:
            failures.append(f"{path.name}: wanted {want}, got {got}")

    if failures:
        print("\nCould not construct every variant from this photo:")
        for f in failures:
            print(f"  {f}")
        print("Try a sharper, higher-resolution, single-subject photo.")
        return 1

    print("\nAll variants verified. Demo sequence:")
    print(f"  python -m faceproof.cli probe data/demo/{stem}_ok.jpg     --subject <id>")
    print(f"  python -m faceproof.cli probe data/demo/{stem}_blurry.jpg --subject <id>")
    print(f"  python -m faceproof.cli probe data/demo/{stem}_tiny.jpg   --subject <id>")
    print(f"  python -m faceproof.cli probe data/demo/{stem}_crowd.jpg  --subject <id>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
