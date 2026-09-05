<div align="center">

# FaceProof

**Consent-gated face identification for on-chain attestation**

Hacker House Goa 2026 · Task 3 · **Stage 1 — the probe**

[![tests](https://github.com/Anbi105/HHGoa2026-Task3-FaceID-Blockchain/actions/workflows/tests.yml/badge.svg?branch=person-1%2Fstage-1-probe)](https://github.com/Anbi105/HHGoa2026-Task3-FaceID-Blockchain/actions/workflows/tests.yml)
[![coverage](https://img.shields.io/badge/coverage-97%25-brightgreen)](#tests)
[![tests count](https://img.shields.io/badge/tests-167-brightgreen)](#tests)
[![python](https://img.shields.io/badge/python-3.11%20|%203.12%20|%203.13%20|%203.14-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![model](https://img.shields.io/badge/model-InsightFace%20buffalo__l-orange)](DECISIONS.md)
[![stage](https://img.shields.io/badge/stage-1%20of%203-informational)](#where-this-sits)

*A face never becomes a vector without consent. A withdrawn consent makes every past commitment unverifiable — including one already written to an immutable chain.*

</div>

---

## What this does

Turns an image into a **512-dimensional ArcFace embedding** — or refuses, and says exactly why. Then commits to that embedding without ever revealing it, and hands Stage 2 a serialised artifact it can read from disk.

```mermaid
flowchart LR
    IMG[/"probe image"/] --> CG{{"CONSENT GATE"}}
    CG -->|"no valid consent"| REF["REFUSED<br/>exit 2"]
    CG -->|"granted, in scope,<br/>unexpired"| DET["SCRFD<br/>detect"]
    DET --> QG{{"quality gate<br/>4 checks"}}
    QG -->|"fails"| ABS["ABSTAIN<br/>exit 1"]
    QG -->|"passes"| ENC["ArcFace 512-d<br/>L2-normalised"]
    ENC --> COM["keccak256 commitments"]
    COM --> OUT[("out/run-id/")]
    ABS --> OUT
    OUT --> S2["Stage 2<br/>discovery"]
    S2 --> S3["Stage 3<br/>attestation"]

    classDef gate fill:#7c3aed,stroke:#5b21b6,color:#fff
    classDef bad fill:#dc2626,stroke:#991b1b,color:#fff
    classDef warn fill:#d97706,stroke:#92400e,color:#fff
    classDef good fill:#059669,stroke:#065f46,color:#fff
    classDef next fill:#64748b,stroke:#475569,color:#fff,stroke-dasharray:4 3
    class CG,QG gate
    class REF bad
    class ABS warn
    class ENC,COM,OUT good
    class S2,S3 next
```

> [!IMPORTANT]
> **The consent gate runs before `cv2.imread`.** For a subject with no valid consent, no image is read, no face is detected, and no vector is computed. `test_refusal_happens_before_detection` asserts the detector is never called on that path — the refusal is provably inert, not a printed disclaimer.

---

## Quick start

```bash
git clone -b person-1/stage-1-probe https://github.com/Anbi105/HHGoa2026-Task3-FaceID-Blockchain.git
cd HHGoa2026-Task3-FaceID-Blockchain
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

```bash
make setup    # pre-download model weights (~330 MB) — do this BEFORE recording
make test     # 167 tests, ~0.4s, no model and no network required
```

> [!TIP]
> `make setup` exists because of the unedited-recording constraint. Nothing on the critical path may be slow, so the weights are staged before the camera rolls.

---

## The demo

`make demo` runs the whole sequence. Steps **2** and **7** are the point.

<table>
<tr><th align="center">#</th><th align="left">Command</th><th align="left">What the camera sees</th></tr>
<tr><td align="center">1</td><td><code>make config</code></td><td>Every parameter in force, printed from the same object the run uses</td></tr>
<tr><td align="center"><b>2</b></td><td><code>make probe</code></td><td>🔴 <b>REFUSED</b> — <code>no_consent_on_record</code>. Nothing was read.</td></tr>
<tr><td align="center">3</td><td><code>make consent-grant SUBJECT=alice</code></td><td>Token + 256-bit salt created, stored locally at mode 600</td></tr>
<tr><td align="center">4</td><td><code>make probe SUBJECT=alice</code></td><td>🟢 <b>PASS</b> → <code>probe.json</code>, <code>embedding.f32</code>, <code>manifest.jsonl</code></td></tr>
<tr><td align="center">5</td><td><code>make probe SUBJECT=alice IMAGE=data/demo/noface.jpg</code></td><td>🟡 <b>ABSTAIN</b> — a correct outcome, with its own record</td></tr>
<tr><td align="center">6</td><td><code>make consent-revoke SUBJECT=alice</code></td><td>🔥 Salt <b>DESTROYED</b></td></tr>
<tr><td align="center"><b>7</b></td><td><code>make probe SUBJECT=alice</code></td><td>🔴 <b>REFUSED</b> — <code>consent_revoked</code>. The same image, now inert.</td></tr>
</table>

<details>
<summary><b>Actual terminal output, step 4</b></summary>

```
probe run_start      run_id=20260905T182509Z-4eb565  image=data/demo/synthetic_face.jpg
probe config         model=insightface/buffalo_l@w600k_r50  pipeline=faceproof/1.1.0
probe consent_ok     scope=face_probe_demo  expires_at=2026-10-05T18:25:08Z
                     subject_commitment=0x4be251521df89d44...
probe quality_gate   result=PASS  det_score=0.7729  face_px=199  blur_var=827.38  n_faces=1

╭──────────────────────────────────────────────────────────╮
│ QUALITY_GATE=PASS                                        │
╰──────────────────────────────────────────────────────────╯

probe encoded        dim=512  dtype=float32  l2_norm=1.0
probe artifact       path=out/run-.../embedding.f32  bytes=2048  sha256=1169bd9fa8777d67...
probe commitment     embedding=0x81956d3dc0ac9d31ef8eb2377c7f25e4...
probe commitment     subject=0x4be251521df89d44c14d2eb3156d272e...
probe run_end        status=accepted
```

Every line lands in `manifest.jsonl` with a timestamp and an elapsed offset. A silent pipeline that prints `Done` proves nothing on video.

</details>

---

## The quality gate

Checks run in order. The first failure reports **the value and the threshold it missed**, so the reason explains itself on camera.

| # | Check | Gate | Rejection reason |
|:-:|-------|:----:|------------------|
| 0 | Readable | — | `unreadable_image` |
| 1 | Face present | — | `no_face_detected` |
| 2 | Detection confidence | `≥ 0.62` | `low_detection_confidence:0.31<0.62` |
| 3 | Face size, shorter side | `≥ 90 px` | `face_too_small:50px<90px` |
| 4 | Blur, Laplacian variance | `≥ 45.0` | `image_too_blurry:3.9<45.0` |
| 5 | Single subject | `secondary/primary ≤ 0.60` | `ambiguous_subject:2_faces_ratio_0.99>0.6` |

> [!NOTE]
> Check 5 is the one people skip. Group photos are the most common realistic input, and silently picking the largest face is how you produce a confidently wrong match on video. A blurry, angled or 40-pixel face produces an embedding that is *confidently wrong* — reject early and say why.

**Exit codes:** `0` accepted · `1` abstain · `2` refused, no consent · `3` usage error.

---

## Consent, commitments, erasure

```bash
make consent-grant  SUBJECT=alice
make consent-list
make consent-revoke SUBJECT=alice
```

A grant mints a random consent token and a **256-bit per-subject salt**, stored at `data/consent/store.json` (mode `600`, gitignored). Neither ever leaves the host.

Exactly two values cross into the attestation path, both opaque 32-byte digests:

| Leaf | Value | Why it carries nothing |
|------|-------|------------------------|
| subject | `keccak256(consent_token)` | The token is a random UUID4. It commits to a *consent event*, not to a person — two grants to the same subject produce unrelated digests. |
| probe | `keccak256(salt ‖ embedding)` | Commits to the face without carrying it. Little-endian float32, pinned by golden tests so the encoding cannot drift. |

> [!WARNING]
> **Revocation destroys the salt and keeps the record.** Afterwards, reproducing an anchored `keccak256(salt ‖ embedding)` means guessing 256 bits — including for a root already written to an immutable chain. The record survives so the withdrawal stays auditable.
>
> This is the erasure path, and `test_commitment_unverifiable_after_erasure` asserts it. The guarantee is **"unverifiable"**, not "deleted" — see [LIMITATIONS.md](LIMITATIONS.md#9-erasure-covers-this-host-not-copies).

---

## Stage 2 contract

Stage 2 reads the run directory. It does not import Stage 1's objects — that boundary is what lets each stage run alone, resume after a mid-recording failure, and prove Stage 3 could not have influenced Stage 2.

```python
from faceproof.handoff import load_record, read_embedding

run = "out/run-20260905T182509Z-4eb565"
record = load_record(run)
vector = read_embedding(run)          # (512,) float32, L2-normalised

if record["status"] == "accepted":
    hits = index.search(vector)       # your FAISS query
else:
    record["rejection_reason"]        # "image_too_blurry:3.9<45.0"
```

<details>
<summary><b>What <code>out/run-&lt;id&gt;/</code> contains</b></summary>

| File | Contents | Safe to show? |
|------|----------|:-------------:|
| `probe.json` | Status, quality measurements, the gate that was applied, full config, image digest, both commitments | ✅ no biometrics, no PII |
| `embedding.f32` | The raw 512-d vector, little-endian float32, 2048 bytes | ❌ **local only**, gitignored |
| `manifest.jsonl` | Append-only run log with artifact digests | ✅ |

</details>

<details>
<summary><b>Why every number in <code>probe.json</code> is a string</b></summary>

```json
"quality": {
  "det_score": "0.772918",
  "blur_var":  "827.384790",
  "face_px":   199
}
```

A bare float that reaches a serialised record is the classic cause of a proof that verifies locally and fails against the chain — `repr` differs across machines and the bytes stop matching. Every number goes through `q()`, and `_reject_floats` raises loudly if one survives. **Do not weaken it.**

Stage 3's `canonical.py` will define the same `q()`. The two must stay byte-identical or leaf 0 will not reproduce — import this one rather than writing a second.

</details>

The in-process API is still available:

```python
from faceproof import encode, cosine

probe, reason = encode("photo.jpg")
if probe is None:
    print(reason)              # a str subclass — ==, startswith, f-strings all work…
    print(reason.metrics)      # …carrying what was measured, so no second detection pass
else:
    probe.embedding            # (512,) float32
```

---

## Calibration

> [!CAUTION]
> **Not yet measured.** `accept_at = 0.55` is the guide's placeholder, not a result. `make config` prints a warning while `data/calibration.json` is absent, so the recording cannot accidentally imply otherwise.

```
data/calib/<subject_id>/*.jpg      # 2+ subjects, 5–10 images each, varied lighting and angle
```

```bash
make calibrate      # writes data/calibration.json — commit it
```

The output records **both full score distributions** and a sha256 fingerprint of the exact image set, so the number is auditable rather than asserted. It turns *"we used 0.5"* into *"we measured a true-accept rate of 0.94 at zero false accepts on our own held-out pairs, so we set the gate at 0.57."*

<details>
<summary><b>Why synthetic faces cannot substitute — measured, not assumed</b></summary>

ArcFace maps drawings into a narrow region of the embedding space. Across four visually distinct synthetic subjects:

| | genuine | impostor | separation |
|---|:---:|:---:|:---:|
| synthetic faces | 0.85 | **0.71** | 0.05 |
| real faces (typical) | 0.85 | ~0.30 | >0.30 |

An impostor mean of 0.71 sits far above any usable threshold, so a number measured on them would look like evidence and be worthless. The fixtures are also detector-fragile: blurring drops `det_score` to 0.54 (rejecting for *low confidence*, not blur), and downscaling or side-by-side composition makes them undetectable entirely.

So the synthetic set supports exactly two branches — `PASS` and `no_face_detected`. For the rest, derive from a real consenting photo:

```bash
make demo-variants SRC=path/to/photo.jpg
```

That script searches for the mildest transform landing in each intended branch and **verifies every image it writes** against the real detector, rather than assuming a fixed blur radius works.

</details>

---

## Tests

```bash
make test    # 167 tests, ~0.4s
make cov     # 97% statement coverage
```

| Property | Status |
|----------|--------|
| Model weights required | ❌ none — `insightface` is imported lazily inside `app()` |
| Network required | ❌ none |
| Writes outside `tmp_path` | ❌ none — an autouse fixture repoints `data_dir` and `out_dir` |
| Passes under `python -O` | ✅ no behaviour hidden behind `assert` |
| CI matrix | Python 3.11 · 3.12 · 3.13 |

**Mutation-checked.** Each of these breaks at least one test:

| Mutation | Caught by |
|----------|-----------|
| `SAFETY_MARGIN` 0.03 → 0.99 | `test_threshold_follows_the_rule` |
| `overlap_warning` hardwired `False` | `test_separation_and_overlap_flag_agree` |
| Blur gate disabled | `test_image_too_blurry` |
| Ambiguity gate disabled | `test_ambiguous_subject` |
| Largest-face sort removed | `test_largest_face_is_selected` |
| Embedding byte encoding changed | `test_embedding_bytes_are_pinned` |

> [!NOTE]
> The golden-vector tests in `test_golden.py` pin the embedding encoding and the resulting commitment to fixed hex, and assert Ethereum `keccak256` rather than NIST SHA3. If one fails, **do not update the expected value** — a changed encoding invalidates every commitment already anchored.

---

## Where this sits

| Stage | Scope | Modules | Status |
|:-----:|-------|---------|--------|
| **1** | **Probe** — detect, gate, encode, consent-bind | `config` `manifest` `face` `consent` `handoff` `calibrate` `cli` | ✅ **complete** · calibration data pending |
| 2 | Discovery — social index + reverse image search | `ingest_bsky` `index` `channel_a` `channel_b` `fuse` | ⬜ not started |
| 3 | Attestation — canonicalise, commit, anchor, verify | `canonical` `merkle` `bundle` `chain` `anchor` `verify` + `contracts/` | ⬜ not started |

```
.
├── faceproof/
│   ├── config.py      all tunables; prints itself into every run      §4
│   ├── manifest.py    append-only JSONL run log                       §4
│   ├── face.py        detection, quality gate, ArcFace encoding       §5
│   ├── consent.py     consent store, commitments, erasure             §8 · D12
│   ├── handoff.py     the Stage 1 → Stage 2 boundary artifact         §2
│   ├── calibrate.py   threshold measurement                           §5 · D3
│   └── cli.py         the recorded surface
├── tests/             167 tests, fully mocked
├── scripts/           fixture generators, self-verifying
└── data/demo/         synthetic smoke-test inputs
```

---

## Design rationale

Fourteen decisions with their trade-offs live in **[DECISIONS.md](DECISIONS.md)** — six from the guide, thirteen specific to this implementation. Highlights:

- **Why the consent check precedes `imread`** — checking after encoding means a biometric already exists for someone who did not agree
- **Why the subject leaf hashes the token, not the subject id** — a 32-byte digest of a short string is trivially brute-forced
- **Why `Rejection` subclasses `str`** — carries its metrics without breaking a single existing caller
- **Why the salt is retained but the record survives revocation** — erasure without destroying the audit trail

Ten honest constraints live in **[LIMITATIONS.md](LIMITATIONS.md)**, including no liveness detection, unmeasured demographic performance, and the fact that erasure covers this host and not copies.

---

<div align="center">
<sub>

Built for the unedited take. Every command is a Makefile target so nothing is typed live,<br/>
and every stage prints its evidence so the viewer never has to take your word for anything.

</sub>
</div>
