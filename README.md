# FaceProof — Stage 1: probe

**Hacker House Goa 2026 · Task 3 · Face Identification & Blockchain Verification**

Consent gate → face detection → quality gate → ArcFace embedding →
commitment → serialised handoff for Stage 2.

```
probe image ──▶ CONSENT GATE ──▶ SCRFD detect ──▶ quality gate ──▶ ArcFace 512-d
                (refuse here,     no consent =                      L2-normalised
                 before any       nothing is                              │
                 biometric)       computed                                ▼
                                                              ┌───────────────────────┐
                                                              │ out/run-<id>/         │
                                                              │  probe.json    ──▶ Stage 2
                                                              │  embedding.f32 (local)│
                                                              │  manifest.jsonl       │
                                                              └───────────────────────┘
```

Nothing on the attestation path carries a biometric: Stage 3 receives two
opaque 32-byte digests, `keccak256(salt‖embedding)` and
`keccak256(consent_token)`.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make setup          # pre-download model weights — do this BEFORE recording
make test           # 160 tests, no model and no network required
```

## The demo sequence

`make demo` runs the whole thing in order. Individually:

```bash
make config                                    # 1. parameters in force
make probe                                     # 2. REFUSED — no consent on record
make consent-grant SUBJECT=alice               # 3. subject consents
make probe SUBJECT=alice                       # 4. accepted, handoff written
make probe SUBJECT=alice IMAGE=data/demo/noface.jpg   # 5. ABSTAIN
make consent-revoke SUBJECT=alice              # 6. salt destroyed
make probe SUBJECT=alice                       # 7. refused again
```

Steps 2 and 7 are the point. A probe for a subject with no valid consent is
refused **before the image is read** — there is a test asserting the
detector is never called on that path.

## Commands

| Command | Purpose |
|---|---|
| `cli setup` | Pre-download model weights (~330 MB) |
| `cli config` | Print the effective configuration |
| `cli consent grant <id> [--scope S] [--days N]` | Record consent |
| `cli consent list` | Show every record and its live status |
| `cli consent revoke <id>` | Withdraw consent, destroy the salt |
| `cli probe <image> --subject <id>` | Run a consent-gated probe |
| `cli calibrate [dir]` | Measure the acceptance threshold |

Exit codes: `0` accepted · `1` rejected by the gate (abstain) · `2` refused
for lack of consent · `3` usage error.

## Quality gate

Checks run in order; the first failure is reported with **the value and the
threshold it missed**, so the reason is self-explaining on video.

| Check | Threshold | Rejection reason |
|---|---|---|
| Readable | — | `unreadable_image` |
| Face present | — | `no_face_detected` |
| Detection confidence | ≥ 0.62 | `low_detection_confidence:0.31<0.62` |
| Face size (shorter side) | ≥ 90 px | `face_too_small:50px<90px` |
| Blur (Laplacian variance) | ≥ 45.0 | `image_too_blurry:3.9<45.0` |
| Single subject | secondary/primary ≤ 0.60 | `ambiguous_subject:2_faces_ratio_0.99>0.6` |

The ambiguity check matters in practice: group photos are the most common
realistic input, and silently picking the largest face is how you produce a
confidently wrong result on camera.

## Stage 2 contract

Stage 2 reads the run directory — it does not import Stage 1's objects:

```python
from faceproof.handoff import load_record, read_embedding

record = load_record("out/run-20260905T182236Z-a1b2c3")
vector = read_embedding("out/run-20260905T182236Z-a1b2c3")   # (512,) float32, L2-normalised

if record["status"] == "accepted":
    ...  # search with `vector`
else:
    record["rejection_reason"]      # e.g. "image_too_blurry:3.9<45.0"
```

`probe.json` carries the status, the quality measurements, the gate that was
applied, the full config, the image digest, and both commitments. Every
number in it is a fixed-precision **string** (D9) — a bare float that reaches
a serialised record is the classic cause of a proof that verifies locally
and fails against the chain, and `_reject_floats` raises if one survives.

The in-process API is still available:

```python
from faceproof import encode, cosine

probe, reason = encode("photo.jpg")
if probe is None:
    print(reason)             # a str subclass…
    print(reason.metrics)     # …that also carries what was measured
else:
    probe.embedding           # (512,) float32, L2-normalised
```

## Consent and erasure

```bash
make consent-grant SUBJECT=alice
make consent-list
make consent-revoke SUBJECT=alice
```

A grant creates a random consent token and a 256-bit per-subject salt,
stored at `data/consent/store.json` (mode 600, gitignored). Neither ever
leaves the host.

Two digests go to Stage 3:

- `keccak256(consent_token)` — commits to a *consent event*, not to a person
- `keccak256(salt ‖ embedding)` — commits to the face without carrying it

Revocation destroys the salt and keeps the record. After that, reproducing
an anchored commitment means guessing 256 bits — including for a root
already written to an immutable chain. That is the erasure path, and
`test_commitment_unverifiable_after_erasure` asserts it.

## Calibration

**Not yet measured.** `accept_at = 0.55` is the guide's placeholder.

```bash
# add 2+ real consenting subjects, 5–10 images each
data/calib/<subject_id>/*.jpg
make calibrate          # writes data/calibration.json — commit it
```

The output records both full score distributions and a sha256 fingerprint of
the exact image set, so the number is auditable rather than asserted.

Synthetic subjects were tried and rejected for this: measured impostor
cosine between different drawn faces is ≈0.71, so any threshold derived from
them would be meaningless. See [LIMITATIONS.md](LIMITATIONS.md).

## Demo images

```bash
make fixtures                              # synthetic; verified against the detector
make demo-variants SRC=path/to/photo.jpg   # blur/size/ambiguity from a real photo
```

The synthetic fixtures only support the PASS and `no_face_detected` branches —
a blurred or downscaled drawing becomes undetectable, so it would demonstrate
the wrong rejection. Both scripts verify every image they write and fail
loudly instead of shipping a fixture that does not do what it claims.

## Tests

```bash
make test    # 160 tests, ~0.4s
make cov     # 97% statement coverage
```

Fully mocked: no model download, no network, no writes outside `tmp_path`.
The suite is mutation-checked — disabling the blur gate, the ambiguity gate,
the largest-face selection, the calibration threshold rule or the overlap
warning each fails at least one test.

## Layout

```
faceproof/
├── config.py      all tunables; prints itself into every run
├── manifest.py    append-only JSONL run log (§4)
├── face.py        detection, quality gate, ArcFace encoding (§5)
├── consent.py     consent store, commitments, erasure (§8, D12)
├── handoff.py     the Stage 1 → Stage 2 boundary artifact (§2)
├── calibrate.py   threshold measurement (§5, D3)
└── cli.py         the recorded surface
```

See [DECISIONS.md](DECISIONS.md) for why each choice was made and
[LIMITATIONS.md](LIMITATIONS.md) for what this does not do.
