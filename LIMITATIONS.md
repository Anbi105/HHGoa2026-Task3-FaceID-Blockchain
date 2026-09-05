# Known limitations — Stage 1 (probe)

Written before they were needed, and deliberately honest. Everything below
is a real constraint of what is in this repository today, not a hypothetical.

## 1. The acceptance threshold is not yet measured

`accept_at = 0.55` is **the guide's placeholder, not a measurement**.
`data/calibration.json` does not exist because calibration requires real
consenting subjects and none are in the repository.

Until you run `make calibrate` on 2+ real subjects, do not claim a
calibrated threshold on camera. `python -m faceproof.cli config` prints a
warning while the file is absent, so the recording cannot accidentally
imply otherwise.

**Why not synthetic subjects.** This was tried and measured, not assumed.
ArcFace maps synthetic faces into a narrow region of the embedding space:
across four visually distinct drawn subjects, impostor cosine averaged
**0.71** with genuine at 0.85 — a separation of 0.05, against a real-face
separation typically above 0.3. A threshold measured on drawings would look
like evidence and be worthless. See `data/calib/README.md`.

## 2. The synthetic fixtures exercise only two gate branches

`data/demo/synthetic_face.jpg` (PASS) and `noface.jpg` (`no_face_detected`)
are the only branches a drawing can honestly demonstrate. Measured on the
real detector:

| Variant | Result |
|---|---|
| blurred cartoon | detection drops to 0.54 → rejected for *low confidence*, not blur |
| downscaled cartoon | undetectable at every scale from 0.50 down to 0.20 |
| two cartoons side by side | undetectable |

For the blur, size and ambiguity branches, derive variants from a real
consenting photo:

```bash
make demo-variants SRC=path/to/photo.jpg
```

That script searches for the mildest transform that lands in the intended
branch and **verifies each variant against the detector**, rather than
assuming a fixed blur radius works.

Related: cartoon detection turned out to be sensitive to JPEG compression
artifacts — an image can be detected on disk and undetectable in memory. The
fixture generator therefore verifies after writing, and fails loudly.

## 3. Environment deviates from the guide's pin set

The guide specifies Python 3.11 with `numpy<2`. This checkout runs
**Python 3.14 with numpy 2.5.2**, because numpy 1.x has no 3.14 wheels.

The installed set is verified working and fully pinned in
`pyproject.toml` and `requirements.lock.txt`. If you reproduce on another
machine, use Python 3.14 with the lockfile, or move to 3.11 and take the
guide's `numpy<2` pin — do not mix.

## 4. Quality-gate thresholds are defaults, not measurements

`min_det_score=0.62`, `min_face_px=90`, `min_blur_var=45.0` and
`max_secondary_face_ratio=0.60` come from the guide. They are plausible and
they are enforced, but they were not tuned against a labelled set of
acceptable and unacceptable probes. Blur variance in particular is
resolution- and content-dependent: a sharp 4000px photo and a sharp 400px
photo do not produce comparable Laplacian variance.

## 5. Consent is asserted locally, not verified against an authority

`ConsentStore` records that consent was granted, when, for what scope, and
until when. It cannot prove that the person operating the CLI is the person
who consented, and it has no external attestation. This is appropriate for a
demonstration; a production system needs the subject to sign the consent
token with a key they control.

## 6. Liveness and presentation attacks are out of scope

The quality gate rejects blurry, small, low-confidence and ambiguous
images. It does not detect a photo of a photo, a printed mask, or a screen
replay. A hostile subject can defeat it trivially.

## 7. Demographic performance is unmeasured

`buffalo_l` was chosen partly because published results are materially
better than dlib on South Asian faces (D1), but no per-group error rates
were measured for this deployment. Do not claim fairness properties.

## 8. The raw embedding is written to disk

`out/run-<id>/embedding.f32` holds the unencrypted 512-d vector. It is
gitignored and never leaves the host, but it is genuine biometric data at
rest with no encryption. `make clean-runs` deletes it. Nothing on the
attestation path carries it — only the salted commitment.

## 9. Erasure covers this host, not copies

Revoking consent destroys the salt in the local store, which makes any
anchored commitment unverifiable. It cannot reach a salt that was backed
up, copied, or exfiltrated before revocation, and it cannot remove an
already-anchored root from a chain. The guarantee is "unverifiable", not
"deleted".

## 10. Single-face pipeline

Exactly one subject per probe. A group photo where a second face exceeds
60% of the primary's area is rejected rather than resolved. This is
deliberate — silently picking the largest face is how you produce a
confidently wrong result on video — but it means the system cannot process
group photos at all.
