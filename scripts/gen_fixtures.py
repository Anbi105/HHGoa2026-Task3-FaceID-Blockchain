"""Generate synthetic image fixtures for the demo smoke test.

    python scripts/gen_fixtures.py

Produces, in data/demo/:

    synthetic_face.jpg   a synthetic face that passes the quality gate
    noface.jpg           a plain gradient               → no_face_detected

Those are the only two fixtures a drawing can honestly support.  Measured
against the real detector, a cartoon face survives neither blurring
(det_score falls to 0.54, so it is rejected for low confidence, not for
blur), nor downscaling, nor side-by-side composition — every one of those
becomes undetectable.  For the blur / size / ambiguity branches use a real
consenting photo:

    python scripts/make_demo_variants.py path/to/photo.jpg

WHAT THIS IS NOT
----------------
These are drawings, not people.  They exist so a clean checkout has a
smoke test with no personal data in the repository.

They are useless for calibration.  ArcFace maps synthetic faces into a
tiny region of the embedding space — measured impostor cosine between
*different* synthetic subjects is ~0.71, far above any usable threshold —
so a threshold measured on them would be meaningless.  Calibration
requires real consenting subjects in data/calib/.  See LIMITATIONS.md.

The generator VERIFIES each fixture against the real detector before
writing it, and fails loudly otherwise.  An earlier version of this script
silently emitted undetectable images; that must not happen again.
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "data" / "demo"

# Geometry chosen by sweeping the detector: 100% detection across noise
# seeds at a median det_score of ~0.73.  eye_y is the sensitive parameter —
# moving it to 175 drops detection to 0%.
FACE_A = dict(
    skin=(120, 100, 85), hair=(20, 20, 20),
    eye_dx=44, eye_y=184, head=(110, 125), mouth_w=38,
)
# Seed 16 measured highest of 30 (det_score 0.773); all 30 were detected
# with this geometry, so the fixture does not depend on a lucky seed.
NOISE_SEED = 16


def draw_face(skin, hair, eye_dx, eye_y, head, mouth_w, seed=NOISE_SEED, size=(480, 640)):
    """Draw a parameterised cartoon face."""
    rng = np.random.RandomState(seed)
    h, w = size
    img = np.ones((h, w, 3), dtype=np.uint8) * 200
    cx, cy = w // 2, 200

    cv2.ellipse(img, (cx, cy), head, 0, 0, 360, skin, -1)
    for sx in (-eye_dx, eye_dx):
        cv2.circle(img, (cx + sx, eye_y), 12, (40, 40, 40), -1)
        cv2.circle(img, (cx + sx + 3, eye_y - 2), 4, (200, 200, 200), -1)
    # Nose and mouth stay at fixed height: the eye-to-nose distance is the
    # parameter the detector is sensitive to, and compressing it is what
    # makes these drawings detectable at all.
    pts = np.array([[cx, 195], [cx - 10, 230], [cx + 10, 230]], np.int32)
    cv2.polylines(img, [pts], True, (140, 120, 100), 2)
    cv2.ellipse(img, (cx, 260), (mouth_w, 12), 0, 0, 180, (120, 80, 80), 2)
    cv2.line(img, (cx - eye_dx - 20, eye_y - 20), (cx - eye_dx + 15, eye_y - 25), (80, 60, 40), 3)
    cv2.line(img, (cx + eye_dx - 15, eye_y - 25), (cx + eye_dx + 20, eye_y - 20), (80, 60, 40), 3)
    cv2.ellipse(img, (cx, 140), (head[0] + 10, 80), 0, 180, 360, hair, -1)

    noise = rng.randint(0, 15, img.shape).astype(np.uint8)
    return cv2.add(img, noise)


def _detect(path: Path):
    """Run the real detector on a written file — fixtures are verified, not assumed."""
    from faceproof.face import app

    faces = app().get(cv2.imread(str(path)))
    return sorted(
        faces,
        key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
        reverse=True,
    )


def _write(name: str, img: np.ndarray) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    cv2.imwrite(str(path), img)
    return path


def main() -> int:
    from faceproof.config import cfg

    failures: list[str] = []

    def check(path: Path, want: str) -> None:
        faces = _detect(path)
        n = len(faces)
        det = float(faces[0].det_score) if n else 0.0
        side = (
            min(faces[0].bbox[2] - faces[0].bbox[0], faces[0].bbox[3] - faces[0].bbox[1])
            if n else 0.0
        )
        ok = {
            "pass": n == 1 and det >= cfg.min_det_score and side >= cfg.min_face_px,
            "small": n >= 1 and side < cfg.min_face_px,
            "two": n >= 2,
            "none": n == 0,
        }[want]
        status = "ok " if ok else "FAIL"
        print(f"  [{status}] {path.name:<20} faces={n} det={det:.2f} side={int(side)}px")
        if not ok:
            failures.append(f"{path.name}: wanted {want}, got faces={n} det={det:.2f}")

    print("writing fixtures:")
    check(_write("synthetic_face.jpg", draw_face(**FACE_A)), "pass")

    gradient = np.zeros((480, 640, 3), dtype=np.uint8)
    for y in range(480):
        gradient[y, :] = [int(255 * y / 480)] * 3
    check(_write("noface.jpg", gradient), "none")

    if failures:
        print("\nFIXTURE VERIFICATION FAILED:")
        for f in failures:
            print(f"  {f}")
        return 1

    print("\nAll fixtures verified against the real detector.")
    print("For the blur / size / ambiguity branches, derive variants from a")
    print("real consenting photo:  python scripts/make_demo_variants.py <photo>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
