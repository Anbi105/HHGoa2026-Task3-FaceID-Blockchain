# Calibration set

Threshold calibration (§5, D3) requires **real consenting subjects**.
This directory is intentionally empty in the repository — it holds
biometric data and is gitignored.

## Layout

```
data/calib/
├── <subject_id>/
│   ├── 01.jpg
│   ├── 02.jpg      ← 5–10 images per subject, varied lighting and angle
│   └── ...
└── <another_subject>/
    └── ...
```

Minimum: **2 subjects, 2 images each**. Useful: **3+ subjects, 5–10 images each**.

## Run

```bash
make calibrate           # or: python -m faceproof.calibrate data/calib
```

This writes `data/calibration.json` — commit that file. It is two kilobytes
and it is the strongest single piece of evidence in the repository that the
matching threshold was engineered rather than tuned until the demo passed.
Then set `accept_at` in `faceproof/config.py` (or `FACEPROOF_ACCEPT_AT`) to
the measured `suggested_accept_at`.

## Why not synthetic images

Synthetic faces were measured and rejected for this purpose: ArcFace maps
drawings into a narrow region of the embedding space, with impostor cosine
between *different* synthetic subjects around 0.71 — far above any usable
threshold. A number measured on them would be meaningless. See LIMITATIONS.md.
