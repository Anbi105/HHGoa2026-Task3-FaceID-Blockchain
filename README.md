<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/hero-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/hero-light.svg">
  <img alt="FaceProof — consent-gated face identification for on-chain attestation" src="assets/hero-light.svg" width="100%">
</picture>

<br/>

[![tests](https://github.com/Anbi105/HHGoa2026-Task3-FaceID-Blockchain/actions/workflows/tests.yml/badge.svg?branch=person3-blockchain)](https://github.com/Anbi105/HHGoa2026-Task3-FaceID-Blockchain/actions/workflows/tests.yml)
[![coverage](https://img.shields.io/badge/coverage-93%25_core_·_68%25_all-d29922?labelColor=1f2328)](#tests)
[![python tests](https://img.shields.io/badge/pytest-305-3fb950?labelColor=1f2328)](#tests)
[![foundry](https://img.shields.io/badge/forge_test-10%20passing-3fb950?labelColor=1f2328)](#foundry-tests)
[![solidity](https://img.shields.io/badge/solidity-0.8.24-363636?logo=solidity&logoColor=white&labelColor=1f2328)](contracts/src/EvidenceRegistry.sol)
[![python](https://img.shields.io/badge/python-3.11%20|%203.12-3776AB?logo=python&logoColor=white&labelColor=1f2328)](pyproject.toml)
[![stage](https://img.shields.io/badge/stage_3-attestation-8250df?labelColor=1f2328)](#stage-3--blockchain-attestation)

**Team OneReign** · **A face never becomes a vector without consent — and it never becomes a row on a chain at all.**<br/>
Only cryptographic commitments are anchored. Withdraw consent and every past commitment becomes unverifiable — including one already written to an immutable chain.

</div>

---

## The pipeline

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/pipeline-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/pipeline-light.svg">
  <img alt="Pipeline: probe image, consent gate, SCRFD detect, quality gate, ArcFace 512-d, keccak256 commitments, run directory" src="assets/pipeline-light.svg" width="100%">
</picture>

> [!IMPORTANT]
> **The consent gate runs before `cv2.imread`.** For a subject with no valid consent, no image is read, no face is detected, and no vector is computed. `test_refusal_happens_before_detection` asserts the detector is never called on that path — the refusal is provably inert, not a printed disclaimer.

| Stage | What it does |
|:-----:|--------------|
| **1 of 3 — Face Identity / Probe** | Detect a face, apply the quality gate (detector confidence, face size, blur, multi-face ambiguity), encode to a 512-d L2-normalised vector, bind it to a consent grant, and write the handoff record. Modules: `config` `manifest` `face` `consent` `handoff` `calibrate` `cli`. |
| **2 of 3 — Evidence Discovery / Matching** | Search the probe against a self-built public-post face index (Channel A) and reverse-image search (Channel B), re-score every candidate locally, and fuse the channels into `corroborated`, `single_channel_{a,b}`, or `abstain`. Owned by Person 2 (branch `person2`, vendored under `vendor/stage2/`); reached from the root pipeline through `faceproof/stage2_bridge.py`, which runs Person 2's `fuse` / `channel_b` / `index.search` and writes `stage2.json`. |
| **3 of 3 — Blockchain Attestation** | Canonicalise the accepted evidence into eight field groups, commit each to a keccak256 Merkle leaf, build the root, anchor it on chain, then independently re-verify, prove selective disclosure, and demonstrate tamper detection. Modules: `canonical` `merkle` `bundle` `stage2_adapter` `chain` `anchor` `verify` `run` + `contracts/`. |

Stage 3 takes the evidence the earlier stages produced and turns it into a **reproducible, tamper-evident cryptographic attestation**: eight canonical evidence groups → eight Merkle leaves → one root → one on-chain record. Anyone can later recompute the root from the bundle and check it against the chain.

> [!NOTE]
> **Live on Polygon Amoy** (chain id `80002`): `EvidenceRegistry` [`0xeE0efb2a3D75f1933f171dE8e8D9Dd14903170d3`](https://amoy.polygonscan.com/address/0xeE0efb2a3D75f1933f171dE8e8D9Dd14903170d3), deploy tx [`0xdf7bf9…5be79`](https://amoy.polygonscan.com/tx/0xdf7bf97cc2e1661efabfe60e1a367440f5e5119a4df1e15c48c425389785be79) (block `46888484`), anchor id `0` tx [`0x4365d1…980b8`](https://amoy.polygonscan.com/tx/0x4365d17c38ea8851ca18f62486b4f7471ab1b8023f9078c672e1c4552ab980b8) (block `46888956`). Anvil (chain id `31337`) is the deterministic offline fallback and needs no keys. Full three-stage run: [`application.md`](application.md).

> [!CAUTION]
> **No raw biometric data on chain. Ever.**
> The 512-d face embedding, the consent token, the post text and the image bytes never enter the bundle and never touch the blockchain. Only `keccak256` / `SHA-256` commitments, hashes and public metadata are anchored.

---

## See it run

Every command in this section is a Makefile target, so nothing is typed live during the take. This is real output, not a mock-up.

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/demo-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/demo-light.svg">
  <img alt="Terminal transcript: probe refused, consent granted, probe accepted, consent revoked, probe refused again" src="assets/demo-light.svg" width="760">
</picture>
</div>

The arc is the argument. The **same image** is refused, then accepted, then refused again — and the third refusal is permanent, because revocation destroyed the salt.

```bash
make demo    # runs exactly the sequence above (Stage 1)
```

---

## Quick start

### Clone and install

> [!IMPORTANT]
> **Build the venv with Python 3.11 or 3.12 explicitly — not bare `python3`.**
> `pyproject.toml` declares `requires-python = ">=3.11,<3.13"`, so on a machine
> whose `python3` is newer the install fails with
> `Package 'faceproof' requires a different Python: 3.14.x not in '<3.13,>=3.11'`.
> Check with `python3 --version` before creating the venv, and name the
> interpreter version explicitly if it is out of range.

```bash
git clone https://github.com/Anbi105/HHGoa2026-Task3-FaceID-Blockchain.git
cd HHGoa2026-Task3-FaceID-Blockchain

python3 --version                      # must report 3.11.x or 3.12.x
python3 -m venv .venv                  # if it does not, install 3.12 and use it:
                                       #   macOS:  brew install python@3.12
                                       #           /opt/homebrew/bin/python3.12 -m venv .venv
                                       #   Ubuntu: sudo apt install python3.12-venv
                                       #           python3.12 -m venv .venv
```

**Linux / macOS / WSL** — the Makefile hard-codes `.venv/bin/python`, so install into that venv and there is no need to activate it:

```bash
.venv/bin/pip install -e ".[dev]"
```

**Windows (PowerShell or Git Bash)** — activation is unreliable, so call the interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

`[dev]` installs everything — the Stage 1 model stack, the Stage 2 index and the
attestation core — plus the test tooling. The install is split into extras so a
third party can re-verify a bundle without any of the face stack:

| Install | What you get | Needs a C toolchain? |
|---------|--------------|:---:|
| `pip install faceproof` | attestation core only — canonical JSON, Merkle, registry client, `faceproof.verify_cli` | no |
| `pip install "faceproof[probe]"` | adds Stage 1: InsightFace, ONNX Runtime, OpenCV, `numpy<2` | yes on Windows |
| `pip install "faceproof[stage2]"` | adds `faiss-cpu` for Channel A | no |
| `pip install -e ".[dev]"` | all of the above + `pytest` | yes on Windows |

**Python 3.11–3.12.** `numpy` is pinned `<2` for the InsightFace / faiss ABI, and
numpy 1.26.4 publishes no cp313 wheel — so 3.13 is out of range for `[probe]`.

`insightface` and `stringzilla` ship no Windows wheels and build from source, so
`[probe]` / `[dev]` on Windows also needs [MSVC C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/).
Linux and macOS have a toolchain already.

**Foundry** is required for the smart-contract half (`make deploy`, `make forge-test`,
`make anchor`, and any `--chain` verification). Install it and make sure `forge`,
`anvil` and `cast` are on your `PATH`:

```bash
brew install foundry            # macOS
curl -L https://foundry.paradigm.xyz | bash && foundryup    # Linux / WSL
forge --version && anvil --version
```

Everything except the chain steps works without it — the Python suite, the probe,
the corpus build and local (non-`--chain`) verification all run Foundry-free.

### Download the model weights

Stage 1 needs the InsightFace `buffalo_l` bundle (~330 MB, one time). Do this
before any probe, or the first run pays the download:

```bash
make setup
```

### Run the tests

```powershell
# Windows
.\.venv\Scripts\python.exe -m pytest -q            # full suite
.\.venv\Scripts\python.exe -m pytest -q tests\test_canonical.py tests\test_merkle.py `
  tests\test_bundle.py tests\test_stage2_adapter.py tests\test_verify.py `
  tests\test_run.py tests\test_chain.py            # Stage 3 only
forge test --root contracts                        # smart contract
```

```bash
# Linux / macOS / WSL — the Makefile targets assume .venv/bin/python
make test          # full pytest suite
make stage3-test   # Stage 3 Python tests only
make forge-test    # Foundry contract suite
```

Expected, on a clean checkout with no Anvil node running:

```
300 passed, 5 skipped
```

The 5 skips are `tests/test_chain.py` — they need a live node. Start one
(`make anvil`) in another terminal and the same command reports **305 passed**.
`make forge-test` reports **10 passed**. Neither the Python suite nor the
contract suite needs the model weights or the network.

> [!NOTE]
> The Makefile's `PY := .venv/bin/python` is a POSIX path. On Windows the venv lives in `.venv\Scripts\`, so run the `python -m faceproof.run …` / `pytest` commands directly (shown above) rather than `make`.

<details>
<summary><b>Every Stage 1 command</b></summary>

| Command | Purpose |
|---------|---------|
| `make setup` | Pre-download model weights (~330 MB) |
| `make config` | Print the effective configuration |
| `make consent-grant SUBJECT=alice` | Record consent |
| `make consent-list` | Show every record and its live status |
| `make consent-revoke SUBJECT=alice` | Withdraw consent, destroy the salt |
| `make probe SUBJECT=alice IMAGE=…` | Run a consent-gated probe |
| `make calibrate` | Measure the acceptance threshold |
| `make demo` | The full recorded Stage 1 sequence |
| `make test` / `make cov` | Tests, with coverage |
| `make fixtures` | Regenerate + verify synthetic demo images |
| `make demo-variants SRC=photo.jpg` | Derive gate demos from a real photo |
| `make clean-runs` | Delete `out/` |

Exit codes: `0` accepted · `1` abstain · `2` refused, no consent · `3` usage error.

</details>

<details>
<summary><b>Every Stage 3 command</b></summary>

| Command | `faceproof.run` sub-command | Purpose |
|---------|-----------------------------|---------|
| `make banner` | `banner` | Print the public pipeline configuration |
| `make index-stats` | `index-stats` | Print the index snapshot id / stats (read from Stage 2) |
| — | `stage2 --run-dir <d>` | Run Person 2's real discovery/fusion for a run → `stage2.json` |
| `make search` | `search` | Stage 1 handoff → Stage 2 result → 8-group evidence bundle (add `--real-stage2` to run Person 2 first) |
| `make anchor` | `anchor` | Anchor the latest run's Merkle root on-chain |
| `make verify` | `verify` | Independently re-verify the latest run (`CHAIN=1` adds on-chain checks) |
| `make tamper` | `tamper` | Single-character tamper demonstration |
| `make abstain` | `abstain` | Show the abstain path (quality-gate rejection → no bundle) |
| `make forget` | `forget` | Revoke consent and destroy the erasure salt |
| `make deploy` | `deploy` | `forge build` + deploy `EvidenceRegistry` (`RPC=…` / `ACCOUNT=…` to override) |
| `make anvil` | — | Start a local Anvil node on `:8545` |
| `make forge-test` | — | Run the Foundry contract test suite |
| `make stage3-test` | — | Run only the Stage 3 Python tests |
| — | `ui --port 8765` | Serve the local dashboard on `127.0.0.1` |

Windows equivalent, e.g.: `.\.venv\Scripts\python.exe -m faceproof.run search --img data\demo\synthetic_face.jpg --subject alice`

> [!IMPORTANT]
> **`make search` exits `3` on a clean checkout, and that is correct.** No index
> ships with the repository, so there is no Stage 2 result to consume and Stage 3
> refuses to invent one. You have two honest ways forward:
>
> * **`run search --demo`** — uses the clearly-labelled synthetic Stage 2 fixture
>   (`source: synthetic-stub`). Exercises the whole attestation path with no
>   corpus. Nothing about it claims a real search took place.
> * **Build a corpus first** — `run corpus-local` over consenting photographs,
>   then `run stage2`, then `run search`. This is a genuine FAISS retrieval. See
>   [Channel A corpus](#channel-a-corpus--local-consenting-photographs).
>
> Raising `accept_at` to turn an abstain into a match is not a third option.

> [!CAUTION]
> **`make deploy` used to be broken and the fix changed its interface.** It
> previously passed the key through `ETH_PRIVATE_KEY`, which `forge script` does
> not read — forge fell back to its default sender and every deploy failed. The
> target now delegates to `faceproof.run deploy`, which signs via Anvil's
> `--unlocked` account locally and requires a Foundry keystore off-localhost.
> **`KEY=` is gone; use `ACCOUNT=`:**
>
> ```bash
> make deploy                                   # local Anvil, no key anywhere
> cast wallet import deployer --interactive     # once, for a real chain
> make deploy RPC=https://… ACCOUNT=deployer    # prompts for the passphrase
> ```
>
> `run deploy` also accepts a `--private-key` flag that is **parsed and then
> ignored**. Do not use it; it is a leftover and passing a key there does nothing.

</details>

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Package 'faceproof' requires a different Python: 3.14.x` | `python3` is newer than 3.12 | Recreate the venv with an explicit 3.11/3.12 interpreter — see [Clone and install](#clone-and-install) |
| `make: .venv/bin/python: No such file` | venv missing, or built under Windows layout | `python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"` |
| `forge: command not found` | Foundry not installed or not on `PATH` | `brew install foundry`, or `foundryup`; only chain commands need it |
| `Foundry artifact not found … Run forge build` | `contracts/out/` is gitignored and not yet generated | `make deploy`, or `forge build --root contracts` |
| `no Stage 2 result in out/run-… ` (exit 3) | no index, so nothing to consume | Build a corpus, or pass `--demo` — see the note above |
| Stage 2 prints `ABSTAIN` | genuinely no match above threshold, or no index at all | Real result. Check `run index-stats`; do **not** raise `accept_at` |
| `contract not deployed` / an unexpected Amoy transaction | `.env` is in force and points at Amoy with a real key | Source `scripts/demo-anvil.sh` (or `.ps1`) **before** any chain command |
| Chain checks fail right after a redeploy | Anvil restarted, or a new registry was deployed | Re-source the demo script and redeploy; re-anchor, since a fresh registry has no records |
| Dashboard shows the wrong contract | the UI reads `REGISTRY_ADDRESS` at launch | Restart the server after `make deploy` |
| `no completed run under out/` (exit 3) | every run directory lacks `probe.json` | Stage 1 never finished — check `manifest.jsonl` in the newest run |
| Probe rejected `face_too_small` / `low_detection_confidence` | the gate is working | Use a sharper photo where the face is ≥ 90 px and clearly visible |

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
> Check 5 is the one people skip. Group photos are the most common realistic input, and silently picking the largest face is how you produce a confidently wrong match on video. A blurry, angled or 40-pixel face yields an embedding that is *confidently wrong* — reject early and say why.

---

## Consent, commitments, erasure

A grant mints a random consent token and a **256-bit per-subject salt**, stored at `data/consent/store.json` (mode `600`, gitignored). Neither ever leaves the host.

Exactly two values cross into the attestation path, both opaque 32-byte digests:

| Leaf | Value | Why it carries nothing |
|------|-------|------------------------|
| **subject** | `keccak256(consent_token)` | The token is a random UUID4. It commits to a *consent event*, not a person — two grants to the same subject produce unrelated digests. |
| **probe** | `keccak256(salt ‖ embedding)` | Commits to the face without carrying it. Little-endian float32, pinned by golden tests so the encoding cannot drift. |

> [!WARNING]
> **Revocation destroys the salt and keeps the record.** Afterwards, reproducing an anchored `keccak256(salt ‖ embedding)` means guessing 256 bits — including for a root already on chain. The record survives so the withdrawal stays auditable.
>
> `test_commitment_unverifiable_after_erasure` asserts it. The guarantee is **"unverifiable"**, not "deleted" — see [LIMITATIONS.md](LIMITATIONS.md).

---

## Stage 2 contract

Stage 2 reads the run directory. It does not import Stage 1's objects — that boundary is what lets each stage run alone, resume after a mid-recording failure, and prove Stage 3 could not have influenced Stage 2.

```python
from faceproof.handoff import load_record, read_embedding

run = "out/run-demo"
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
| `probe.json` | Status, quality measurements, the gate applied, full config, image digest, both commitments | ✅ no biometrics, no PII |
| `embedding.f32` | The raw 512-d vector, little-endian float32, 2048 bytes | ❌ **local only**, gitignored |
| `manifest.jsonl` | Append-only run log with artifact digests | ✅ |
| `bundle.json` · `proofs.json` · `receipt.json` | Stage 3 output — see below | ✅ commitments only |

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

Stage 3's `canonical.py` defines the same `q()` (fixed precision 6) and the same float-rejection rule, so a number formatted in Stage 1 survives into the bundle byte-for-byte.

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

## Channel A corpus — local consenting photographs

> **The demo does not use Bluesky data.** No member of this team has a Bluesky
> account, and the one seeded public ingest that ran returned HTTP 504 from the
> Bluesky CDN. Rather than fabricate accounts, posts or embeddings, Channel A is
> built from **real photographs the subjects supplied with consent**. Nothing in
> the corpus or in any bundle built from it claims a social-media origin.

The Bluesky path (`run corpus --handles ...`) is unchanged and still works if a
teammate has an account. The local path feeds the **same** index.

### What is and is not substituted

Only the *source of the records* changes. Everything that decides an identity is
Person 2's unmodified code:

| Step | Where it runs |
|------|---------------|
| detection, quality gate, ArcFace embedding, L2 normalisation | Person 2 `face.probe_image` |
| FAISS `IndexIDMap2(IndexFlatIP(512))`, sidecar, snapshot | Person 2 `index.build` |
| cosine top-k, runner-up, margin, accept/abstain | Person 2 `index.search` |
| channel fusion | Person 2 `fuse.fuse` |
| *record production only* | `faceproof/local_corpus.py` (new) |

There is **no** filename matching, image-equality shortcut, hardcoded identity or
synthetic embedding anywhere in that path. A photograph in which InsightFace
finds no usable face is skipped and counted — the gap between `n_images` and
`n_faces` is reported, never padded.

### Layout

```
data/corpus/<subject>/photo1.jpg      # directory name is the subject label
data/probe/target_probe.jpg           # a DIFFERENT photo of the target
```

Both are gitignored. See [`data/corpus/README.md`](data/corpus/README.md).

**Image requirement:** the detected face must be **at least 90 px** (`min_face_px`)
and score `det_score >= 0.62`. Low-resolution snapshots are rejected — in
practice a photo where the face fills a reasonable part of a >= 600 px image.

### Build and inspect

```bash
python -m faceproof.run corpus-local --root data/corpus
python -m faceproof.run corpus-local --root data/corpus --exclude data/corpus/alice/photo1.jpg
python -m faceproof.run index-stats
```

`--exclude` holds a photograph out of the gallery so it can be used as the probe.
That matters: probing with a file that is itself indexed is a byte-identical
self-lookup and proves nothing about recognition.
`faceproof.local_corpus.probe_is_in_index()` re-checks this by image SHA-256.

### Provenance recorded for a local match

| field | value |
|---|---|
| `platform`, `source_type` | `local-consenting-corpus` |
| `author_did` | `did:local:<subject>` |
| `post_url`, `post_uri` | `local://corpus/<subject>/<filename>` |
| `text_sha256` | SHA-256 of the empty string (there is no post text) |

---

## Calibration

> [!CAUTION]
> **Measured, but on far too small a sample to trust — re-measure before relying on it.**
> `data/calibration.json` **is committed** and `config.py` reads it, so the value
> actually in force is **`accept_at = 0.0967`**, not the 0.55 placeholder. Confirm
> with `make config`, which prints the number and where it came from.
>
> It was derived by the rule `impostor_max + 0.03` from **2 subjects / 6 images —
> 6 genuine and 9 impostor pairs**. Nine impostor pairs cannot establish an
> impostor maximum, so 0.0967 is a weak lower bound on a safe threshold. For
> context, published operating points for `buffalo_l` sit around **0.28–0.40**.
> At 0.0967 almost any face clears the score gate and `min_margin` (0.06) is
> doing most of the real work.
>
> **This is the single highest-value thing to fix.** Collect 5+ consenting
> subjects with 5–10 photos each and re-run `make calibrate`. Until then treat
> every accept as provisional and do not cite an accuracy figure.

```
data/calib/<subject_id>/*.jpg      # 5+ subjects, 5–10 images each, varied lighting and angle
```

```bash
make calibrate      # writes data/calibration.json — commit it
```

The output records **both full score distributions** and a sha256 fingerprint of the exact image set, so the number is auditable rather than asserted.

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

</details>

---

## Stage 3 — blockchain attestation

> [!NOTE]
> **Live on Polygon Amoy (chain id `80002`).** `EvidenceRegistry` is deployed and one evidence root is anchored.
>
> | | |
> |------|------|
> | Registry contract | [`0xeE0efb2a3D75f1933f171dE8e8D9Dd14903170d3`](https://amoy.polygonscan.com/address/0xeE0efb2a3D75f1933f171dE8e8D9Dd14903170d3) |
> | Deployment tx | [`0xdf7bf97cc2e1661efabfe60e1a367440f5e5119a4df1e15c48c425389785be79`](https://amoy.polygonscan.com/tx/0xdf7bf97cc2e1661efabfe60e1a367440f5e5119a4df1e15c48c425389785be79) · block `46888484` |
> | Anchor tx (id `0`) | [`0x4365d17c38ea8851ca18f62486b4f7471ab1b8023f9078c672e1c4552ab980b8`](https://amoy.polygonscan.com/tx/0x4365d17c38ea8851ca18f62486b4f7471ab1b8023f9078c672e1c4552ab980b8) · block `46888956` |
> | Anchored root | `0xbd9643d34189af122492472303311cf2bac38066d9c00b98906a91ad69a0d8fc` |
> | Schema | `faceproof.evidence.v1` — `keccak256` = `0x4db08a5aed7495d51e220b32349500509c6aad15505ad77c9566300ff4f91452` |
>
> This anchor predates the audit fixes on `fix/audit-blockers`: the consent leaf then carried a duplicated `subject_ref`, so a bundle built by current code produces a different root. It was not re-anchored (no testnet spend). The deployed contract also predates `verifyField`'s `proof.length == 3` guard.

Stage 3 consumes the Stage 1 handoff (`probe.json`) and a Stage 2 discovery result, and produces three files under `out/run-<id>/`:

| File | Contents |
|------|----------|
| `bundle.json` | The eight evidence groups + the Merkle root, written as **canonical bytes** |
| `proofs.json` | Per-group inclusion proof (index, leaf, audit path) — the material for selective disclosure |
| `receipt.json` | The on-chain anchor record (chain id, contract address, anchor id, tx hash, block, gas) |

```
probe.json  +  Stage 2 result
        │
        ▼
  stage2_adapter.normalize()        ← raw post text is hashed and dropped here
        │
        ▼
  8 canonical evidence groups       canonical.canon()  → deterministic bytes
        │
        ▼
  8 Merkle leaves                   merkle.leaf() = keccak256(keccak256(bytes))
        │
        ▼
  Merkle root                       sorted-pair keccak, full binary tree of depth 3
        │
        ├─►  bundle.json + proofs.json
        │
        ▼
  EvidenceRegistry.anchor(root, schema, bundleURI)      → receipt.json
        │
        ▼
  independent re-verification  +  selective disclosure  +  tamper demo
```

### 1 · Canonical serialization — `faceproof/canonical.py`

Re-verification must reproduce the exact bytes a leaf was hashed from, on a different machine, later. `canon()` guarantees that:

| Property | How |
|----------|-----|
| Sorted keys | `json.dumps(…, sort_keys=True)` |
| Compact JSON | `separators=(",", ":")` — no whitespace |
| UTF-8, real characters | `ensure_ascii=False` then `.encode("utf-8")` |
| Deterministic | same input → identical bytes, every process, every OS |
| Floating-point rejection | `_reject_floats()` raises `TypeError` on any bare `float` or non-string dict key, recursively |
| Fixed-precision quantities | `q(x, nd=6)` renders every number as a fixed-precision decimal **string** before it enters a group |

Verified byte-for-byte: two independent `search` runs produce **identical `bundle.json` and `proofs.json`**.

### 2 · The eight evidence groups — `faceproof/bundle.py`

The bundle contains **exactly** these eight groups, in this order. The index matters: `match_location` is group 2, and that is the group the selective-disclosure demo reveals.

| # | Group | What it carries | What it never carries |
|:-:|-------|-----------------|-----------------------|
| 0 | `probe` | salted commitment to the face embedding, model ID, detection score, blur variance | the raw 512-d embedding |
| 1 | `consent` | subject reference, consent-token commitment, grant timestamp, scope | the consent token, any subject id |
| 2 | `match_location` | platform, canonical post URL, AT-URI | — |
| 3 | `match_author` | author DID, handle observed at retrieval | — |
| 4 | `match_text` | SHA-256 of the post text, text length | the post text |
| 5 | `match_image` | image SHA-256, perceptual hash, source URL | the image bytes |
| 6 | `scores` | cosine score, margin, threshold, fusion verdict | — |
| 7 | `provenance` | pipeline version, schema ID, index snapshot ID, retrieval timestamp, channels used | — |

> [!IMPORTANT]
> **The raw face embedding is not in the bundle and not on chain.** Group 0 carries only Stage 1's `keccak256(salt ‖ embedding)` digest, reused verbatim. `verify_bundle_privacy()` rejects any bundle that smuggles an `embedding`, `salt`, `token` or vector-shaped field into a group, and `canon()` would reject the raw floats anyway.

### 3 · Cryptographic commitments

Stage 3 **does not compute a new commitment and does not generate a fresh salt.** It reads the two digests Stage 1 already put in `probe.json`:

- `probe.commitment` = `keccak256(salt ‖ little-endian-float32 embedding)` — the salt lives only in the consent store.
- `consent.commitment` = `keccak256(consent_token)`.

Because the salt stays local, **revoking consent (`make forget`) permanently breaks the link** between an anchored root and the face that produced it — the erasure path against an immutable ledger.

### 4 · Merkle commitment — `faceproof/merkle.py`

| Element | Rule |
|---------|------|
| **Leaf** | `keccak256(keccak256(canon(group)))` — the double hash domain-separates leaves from internal nodes |
| **Internal node** | `keccak256(min(a,b) ‖ max(a,b))` — sorted pair, so a proof needs only sibling hashes, no left/right bits |
| **Shape** | exactly a power of two; the bundle always has 8 groups → a full tree of depth 3, no padding |
| **Root** | deterministic function of the eight groups |
| **Proof** | 3 sibling hashes; `verify(leaf, proof, root)` re-walks with the same sorted-pair rule |

**Why it matters, in one sentence:** if one field in one group changes, that group's canonical bytes change, its leaf hash changes, and the Merkle root changes — so any edit to an anchored bundle is detectable by recomputation.

The Python rules are mirrored **byte-for-byte** by the `MerkleLite` library inside the contract, and a Foundry test builds a full 8-leaf tree in Solidity and verifies a Python-shaped proof against it.

### 5 · The evidence bundle

```jsonc
// out/run-<id>/bundle.json  (canonical bytes: keys sorted, no whitespace — pretty-printed here)
{
  "schema_id": "faceproof.evidence.v1",
  "pipeline_version": "faceproof/1.1.0",
  "group_order": ["probe","consent","match_location","match_author",
                  "match_text","match_image","scores","provenance"],
  "merkle_root": "0x…",
  "groups": {
    "probe":    { "commitment": "0x…", "model_id": "…", "det_score": "0.960000", "blur_var": "72.500000" },
    "consent":  { "commitment": "0x…", "granted_at": "…", "scope": "face_probe_demo" },
    "match_location": { "platform": "bluesky", "post_url": "…", "at_uri": "at://…" },
    "match_text":     { "sha256": "…", "length": 55 },
    "scores":        { "cosine": "0.700000", "margin": "0.110000", "threshold": "0.550000", "fusion_verdict": "SINGLE_CHANNEL_A" }
    // …match_author, match_image, provenance
  }
}
```

`group_order` is authoritative; because the file itself is canonicalised (keys sorted), the on-disk `groups` object is alphabetical and all leaf math keys off `group_order`.

### 6 · Smart-contract anchoring — `contracts/src/EvidenceRegistry.sol`

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;
```

| Property | Detail |
|----------|--------|
| Append-only | state is a `Record[]` (push only) + a `root → id` map; no delete, no overwrite |
| No admin | no `owner`, no roles, no access modifiers, no constructor arguments |
| No upgrade | no proxy, no `delegatecall`, no `selfdestruct` |
| Stores per anchor | `root`, `anchoredAt` (block timestamp), `submitter` (`msg.sender`), `schema`, `bundleURI` — **no personal data** |

**Functions**

| Signature | Behaviour |
|-----------|-----------|
| `anchor(bytes32 root, bytes32 schema, string calldata bundleURI) → uint256 id` | reverts `ZeroRoot` on a zero root; reverts `RootAlreadyAnchored` if the root was seen before; else appends a record, emits `Anchored`, returns the new id |
| `total() → uint256` | number of anchored records |
| `get(uint256 id) → Record` | reverts `UnknownAnchor(id)` if out of range |
| `idOf(bytes32 root) → uint256` | reverts `UnknownAnchor` if the root was never anchored |
| `isAnchored(bytes32 root) → bool` | membership check |
| `verifyField(uint256 id, bytes32 leaf, bytes32[] calldata proof) → bool` | on-chain selective-disclosure check via `MerkleLite` (sorted-pair keccak) against anchor `id`'s root |

**Errors:** `ZeroRoot()` · `RootAlreadyAnchored(bytes32 root, uint256 existingId)` · `UnknownAnchor(uint256 id)`
**Event:** `Anchored(uint256 indexed id, bytes32 indexed root, bytes32 indexed schema, string bundleURI, address submitter, uint256 anchoredAt)`

<details>
<summary><b>Contracts layout</b></summary>

| File | Purpose |
|------|---------|
| `contracts/src/EvidenceRegistry.sol` | the registry + `library MerkleLite` |
| `contracts/test/EvidenceRegistry.t.sol` | 10 Foundry tests (no `forge-std` dependency — a minimal `Vm` interface is declared locally) |
| `contracts/script/Deploy.s.sol` | `DeployScript.run()` — deploys the registry inside a broadcast |
| `contracts/foundry.toml` | `solc_version = "0.8.24"`, `src/test/script/out` layout, `[rpc_endpoints]` for `anvil` and `amoy` |

</details>

### 7 · Networks — `faceproof/chain.py`

| Network | Chain ID | RPC | Notes |
|---------|:--------:|-----|-------|
| **Anvil** (local) | `31337` | `http://127.0.0.1:8545` | default; used by the integration tests and the offline demo |
| **Polygon Amoy** | `80002` | `https://polygon-amoy-bor-rpc.publicnode.com` | proof-of-stake → the POA extra-data middleware is injected automatically |

- **RPC config** — `CHAIN` selects `anvil` / `amoy`; `RPC_URL` overrides the endpoint; 30-second HTTP timeout.
- **ABI loading** — strictly from the Foundry build artifact `contracts/out/EvidenceRegistry.sol/EvidenceRegistry.json`. Run `forge build` (or `make deploy`) first; a clear error is raised if the artifact is missing. No hand-maintained ABI.
- **Keys & addresses** — `PRIVATE_KEY` and `REGISTRY_ADDRESS` are read from the environment (`Account.from_key`); nothing sensitive is hard-coded or logged. The only literal key in the repo is the world-known public Anvil dev account, used solely by `make deploy` and the local tests.
- **What goes on chain** — a 32-byte root, a 32-byte schema hash, and a short URI string. Never an embedding, an image, a token, or text.

> [!NOTE]
> **Amoy is live.** `EvidenceRegistry` is deployed at [`0xeE0efb2a3D75f1933f171dE8e8D9Dd14903170d3`](https://amoy.polygonscan.com/address/0xeE0efb2a3D75f1933f171dE8e8D9Dd14903170d3) (deployment tx [`0xdf7bf9…5be79`](https://amoy.polygonscan.com/tx/0xdf7bf97cc2e1661efabfe60e1a367440f5e5119a4df1e15c48c425389785be79), block `46888484`) and anchor id `0` is on chain. The Anvil path exercises the identical `chain.py` code offline.

### 8 · The transaction receipt

`make anchor` recomputes the root from the bundle, refuses if it disagrees with the stored value or if the fusion verdict is `ABSTAIN`, sends `anchor()`, then writes:

```jsonc
// out/run-<id>/receipt.json  — the real Polygon Amoy anchor (chain id 80002).
{
  "anchor_id": 0,
  "chain": "amoy",
  "chain_id": 80002,
  "contract": "0xeE0efb2a3D75f1933f171dE8e8D9Dd14903170d3",
  "root": "0xbd9643d34189af122492472303311cf2bac38066d9c00b98906a91ad69a0d8fc",
  "schema": "faceproof.evidence.v1",
  "bundle_uri": "",
  "submitter": "0x0c1536f9F7fbeCE255576CA3C6A4f833e500B5FD",
  "tx_hash": "0x4365d17c38ea8851ca18f62486b4f7471ab1b8023f9078c672e1c4552ab980b8",
  "block_number": 46888956,
  "gas_used": 179379,
  "status": 1,
  "explorer_url": "https://amoy.polygonscan.com/tx/0x4365d17c38ea8851ca18f62486b4f7471ab1b8023f9078c672e1c4552ab980b8"
}
```

> [!NOTE]
> On a local Anvil run the same file carries `"chain": "anvil"`, `"chain_id": 31337`, `"explorer_url": null`, and a throwaway address / hash that regenerates on every run. Anvil stays the deterministic offline fallback.

### 9 · Independent re-verification & selective disclosure — `faceproof/verify.py`

Verification **does not trust the bundle**. `make verify` (add `CHAIN=1` for the on-chain checks) runs:

1. Load `bundle.json`.
2. **Ignore** `bundle["merkle_root"]` entirely.
3. Re-canonicalise each of the eight groups with `canon()`.
4. Recompute all eight leaves (`keccak256(keccak256(bytes))`).
5. Rebuild the Merkle tree.
6. Recompute the root.
7. Compare it to the stored root **and**, when a receipt is present, to the value returned by `EvidenceRegistry.get()` on chain.
8. Verify a **selective-disclosure proof for `match_location`** — both the proof shipped in `proofs.json` and one regenerated from scratch — locally and via the contract's `verifyField()`.
9. Print one pass/fail verdict.

Selective disclosure means you can reveal **only** group 2 (platform, post URL, AT-URI) and prove it belongs under the anchored root, without revealing the other seven groups.

```
              Stage 3 - independent re-verification
  check                                    | value                  |
  ----------------------------------------- ------------------------ ------
  recomputed root                          | 0xbd9643d34189af12…    |  -
  == stored root                           | 0xbd9643d34189af12…    | PASS
  selective disclosure (tree rebuilt)      | match_location         | PASS
  match_location leaf under anchored root  | proofs.json            | PASS
  == on-chain root                         | EvidenceRegistry.get() | PASS
  on-chain verifyField()                   | match_location         | PASS
  ------------------------------------------------------------------------
  VERIFICATION PASSED
```

### 10 · Tamper detection

> [!IMPORTANT]
> **`make tamper`** changes **exactly one character** in `match_location.post_url`, recomputes everything from scratch (it never re-reads the stored root), and shows verification fail.

Steps: load the bundle → flip the last character of `post_url` → recompute the canonical bytes → recompute the leaves → rebuild the tree → recompute the root → compare to the anchored root → the shipped proof for `match_location` no longer places the tampered leaf under the anchored root.

```
TAMPER DEMONSTRATION
  field          groups.match_location.post_url
  before         https://bsky.app/profile/demo.faceproof.test/post/3ksyntheticdemo
  after          https://bsky.app/profile/demo.faceproof.test/post/3ksyntheticdem0   (1 character changed)
  original root (anchored)                     0xbd9643d34189af12…69a0d8fc
  recomputed root (after 1-char edit)          0x7bf1a420833b4d29…5b43f940
  root still matches anchored value           NO
  selective disclosure against anchored root  FAIL
  --------------------------------------------------------------------------
  original = PASS   tampered = DETECTED
```

Proved by `tests/test_verify.py`: `test_tamper_one_character_breaks_verification`, `test_manual_single_char_edit_fails`, and `test_recompute_ignores_a_forged_stored_root` (replaces `merkle_root` with a lie — verification still fails, because it recomputes).

### 11 · The abstain path

If Stage 1 rejects the probe (quality gate) **or** Stage 2 returns `fusion_outcome = "ABSTAIN"` / no match, Stage 3 **does not manufacture an identity match**:

- `bundle.assemble_groups()` raises `AbstainError` — no bundle is built.
- `make search` catches it, writes an honest `abstain.json` (`schema_id: "faceproof.abstain.v1"`, `status: "ABSTAIN"`, the outcome, the Stage 2 source), and exits `1`.
- `make anchor` independently refuses if there is no `bundle.json` or if `scores.fusion_verdict == "ABSTAIN"`.

No Merkle root, no anchor, no false-positive attestation. Quality-gate rejection stays a first-class result.

### 12 · Privacy

| What | Where it lives | On chain? | In `bundle.json`? |
|------|----------------|:---------:|:-----------------:|
| Raw 512-d face embedding | `out/run-<id>/embedding.f32` (gitignored) | ❌ | ❌ |
| Per-subject salt | `data/consent/store.json` (mode 600, gitignored) | ❌ | ❌ |
| Consent token | consent store | ❌ | ❌ (only `keccak256(token)`) |
| Raw post text | dropped at `stage2_adapter` | ❌ | ❌ (only `SHA-256` + length) |
| Image bytes | not handled by Stage 3 | ❌ | ❌ (only `SHA-256` + phash) |
| Personal identifiers | — | ❌ | ❌ |
| Merkle root, schema hash, bundle URI, submitter address, timestamp | — | ✅ | root also in bundle |

`verify_bundle_privacy()` enforces the middle column on every bundle it builds.

---

### Two spec-conformance fixes in the Channel A path

Both come straight from the guide and neither changes a threshold.

**1. Gallery admission follows the guide, not the probe gate (guide p.20).**
The guide filters *corpus* faces on detector confidence alone
(`if f.det_score < 0.55: continue`). Blur, face-size and secondary-face checks
belong to the *probe* (p.15) — they stop a bad **query** producing a confidently
wrong answer. Person 2's `index.build` reuses `probe_image`, so the strict probe
gate was applied to gallery images too and soft or small photographs could never
be indexed at all. `local_corpus.gallery_config()` passes the guide's gallery
criterion into `probe_image(path, config)` — which takes its thresholds from the
config it is handed — so Person 2's module is unmodified and **Stage 1's probe
gate is completely unchanged** (`det >= 0.62`, `face >= 90px`, `blur >= 45.0`).

**2. The margin is measured against the nearest *different* identity (guide p.45).**
The guide's own failure-modes table:

> *Top-1 is correct but the margin gate rejects it* — several images of the same
> person in the corpus, rank 2 is also them → **compute margin against the best
> hit from a different author, not rank 2 outright.**

`index.search` uses `hits[0] - hits[1]` unconditionally, so a gallery holding two
photographs of one subject makes a *correct* identification look ambiguous. On the
demo run the winner and the runner-up were both `person_b` (0.625082 / 0.602771),
collapsing the margin to 0.022 and abstaining on `ambiguous_neighbourhood`. Measured
against the nearest different identity (`person_a`, 0.005108) the margin is 0.619975.

`accept_at` (0.0967, measured) and `min_margin` (0.06) are untouched. `stage2.json`
records **both** figures — `margin_basis`, `runner_up_subject` and the original
`margin_rank1_rank2` — so the change is auditable rather than silent.

---

## Demo runbook (local, end to end)

Anvil keeps chain state **in memory**, so the registry must be redeployed after
every `anvil` restart.

> [!CAUTION]
> **Always source the demo-environment script before any chain command.**
> A populated `.env` points `CHAIN`/`RPC_URL`/`REGISTRY_ADDRESS` at Polygon Amoy
> and supplies a **real** `PRIVATE_KEY`. A chain command run without the demo
> environment therefore talks to Amoy and signs with that key — at best it fails
> with a confusing "contract not deployed", at worst it spends real testnet POL.
>
> The scripts below shadow those values for the local run and **never edit
> `.env`** (`load_dotenv()` does not override variables already in the
> environment, so exporting wins). They also clear `SERPAPI_KEY`, so Channel B
> cannot transmit a cropped face to a third party during a local demo. Each one
> self-checks the node, the contract code and the anchor count before you start.
>
> | Shell | Script | How to run it |
> |---|---|---|
> | bash / zsh (macOS, Linux, WSL) | `scripts/demo-anvil.sh` | `. ./scripts/demo-anvil.sh` |
> | PowerShell (Windows) | `scripts/demo-anvil.ps1` | `. .\scripts\demo-anvil.ps1` |
>
> Both must be **sourced**, not executed — note the leading dot and space.
> Running them as a subprocess sets the variables in a shell that then exits.
>
> **PowerShell may refuse to run the script** ("running scripts is disabled on
> this system"). Either start the shell as `powershell -ExecutionPolicy Bypass`,
> or allow local scripts once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### macOS / Linux / WSL

```bash
# 0 - local chain, in its own terminal, left running
anvil

# 1 - deploy the registry (no private key is passed: Anvil signs unlocked)
make deploy

# 2 - demo environment. Reads the address from Foundry's broadcast record and
#     self-checks the node, the contract code and the anchor count.
. ./scripts/demo-anvil.sh

# 3 - build Channel A from consenting photographs, holding out the probe.
#     Skip this and Stage 2 will honestly ABSTAIN.
.venv/bin/python -m faceproof.run corpus-local --root data/corpus
.venv/bin/python -m faceproof.run index-stats

# 4 - consent, then Stage 1, on a photo that is NOT in the gallery
.venv/bin/python -m faceproof.cli consent grant <subject>
.venv/bin/python -m faceproof.run probe --img data/probe/target_probe.jpg --subject <subject>

# 5 - Stage 2, then Stage 3 + anchor + verify + tamper.
#     Omit --run-dir and both act on the newest run automatically.
.venv/bin/python -m faceproof.run stage2
.venv/bin/python -m faceproof.run search --anchor

# 6 - dashboard
.venv/bin/python -m faceproof.run ui --port 8765
```

All six on-chain and off-chain checks should print `PASS`, and the tamper demo
should report `DETECTED`. If step 5 says `ABSTAIN`, that is a real result — see
the note under step 3.

### Windows

```powershell
# 0 - local chain, in its own window, left running
anvil

# 1 - deploy the registry (no private key is passed: Anvil signs unlocked)
.\.venv\Scripts\python.exe -m faceproof.run deploy --rpc http://127.0.0.1:8545

# 2 - demo environment. Reads the address from Foundry's broadcast record and
#     self-checks the node, the contract code and the anchor count.
. .\scripts\demo-anvil.ps1

# 3 - build Channel A from consenting photographs, holding out the probe
.\.venv\Scripts\python.exe -m faceproof.run corpus-local --root data/corpus data/calib `
    --exclude data/calib/<subject>/<probe>.jpg
.\.venv\Scripts\python.exe -m faceproof.run index-stats

# 4 - consent, then Stage 1
.\.venv\Scripts\python.exe -m faceproof.cli consent grant <subject>
.\.venv\Scripts\python.exe -m faceproof.run probe --img <held-out photo> --subject <subject>

# 5 - Stage 2, then Stage 3 + anchor + verify + tamper.
#     Omit --run-dir and both commands act on the newest run automatically,
#     so there is no run id to copy on camera.
.\.venv\Scripts\python.exe -m faceproof.run stage2
.\.venv\Scripts\python.exe -m faceproof.run search --anchor

# 6 - dashboard
.\.venv\Scripts\python.exe -m faceproof.run ui --port 8767
```

Re-verify or re-tamper any earlier run at any time (these need only the bundle
and the chain, not the original photographs):

```powershell
.\.venv\Scripts\python.exe -m faceproof.run verify --run-dir out
un-<id> --chain
.\.venv\Scripts\python.exe -m faceproof.run tamper --run-dir out
un-<id>
```

If Stage 2 returns **ABSTAIN**, that is a real result: the top cosine did not
clear `accept_at`. Stage 3 then refuses to build a bundle and writes only
`abstain.json`. Do not raise the threshold to turn it into a match.

`run index-stats` warns when the index is **stale** - i.e. photographs it was
built from are no longer on disk. Rebuild with `corpus-local` before recording,
otherwise the snapshot on camera describes a gallery that can no longer be
re-derived.

---

## The dashboard

A local web view of the same pipeline — configuration, consent records, index
snapshot, every run and its artifacts, and a verify button that runs the real
on-chain checks.

```bash
. ./scripts/demo-anvil.sh                             # inherit the demo chain env
.venv/bin/python -m faceproof.run ui --port 8765      # then open http://127.0.0.1:8765
```

Add `--no-browser` to suppress the automatic browser launch.

**It inherits the environment of the shell that launched it.** Start it without
sourcing the demo script and its chain panel shows whatever `.env` holds — Amoy
and a real key. Restart the server after a redeploy, too: `REGISTRY_ADDRESS` is
read at launch, so a server started before `make deploy` keeps pointing at the
old contract.

Stdlib `http.server` only, no new dependencies. It binds `127.0.0.1`, rejects
non-loopback `Host` headers, serves artifacts from a fixed filename whitelist
with the resolved path re-checked under `out/`, and never accepts or returns
`PRIVATE_KEY` — the anchor step reads it from the process environment exactly as
the CLI does.

| Endpoint | Method | Purpose |
|---|:---:|---|
| `/api/state` | GET | config, calibration, index, chain, consent records, all runs |
| `/api/run?id=<run-id>` | GET | artifacts present for one run |
| `/api/artifact?id=<run-id>&name=<file>` | GET | one whitelisted artifact |
| `/api/pipeline` | POST | run probe → stage2 → bundle (→ anchor); returns a `job_id` |
| `/api/verify` | POST | re-verify a run (`check_chain`); returns a `job_id` |
| `/api/job?id=<job-id>` | GET | poll a job started by either POST |

> [!WARNING]
> `faceproof/ui/` has **no test coverage** (see [Tests](#tests)). It is a view
> over modules that are themselves well covered, but the view itself is
> unverified — for anything load-bearing, confirm with the CLI.

---

## Tests

### Full suite

```bash
make test                                   # macOS / Linux / WSL
.\.venv\Scripts\python.exe -m pytest -q     # Windows
```

```
300 passed, 5 skipped        # no Anvil node running
305 passed                   # with `make anvil` in another terminal
```

| Bucket | Count | Notes |
|--------|:-----:|-------|
| Total collected | 305 | across 23 test modules; no model weights and no network required |
| Skipped without a node | 5 | `test_chain.py` — deploys to a live Anvil and checks a Python-built proof via `verifyField()` |
| Coverage, attestation core | **93%** | `canonical` 100% · `handoff` 100% · `config` 100% · `verify_cli` 100% · `merkle` 98% · `verify` 97% · `bundle` 96% · `consent` 96% · `face` 93% · `anchor` 70% |
| Coverage, `make cov` as printed | **68%** | the headline number is dragged down by the dashboard — see below |

> [!WARNING]
> **The `faceproof/ui/` package has no tests at all** — 615 statements at 0%
> coverage, and `.coveragerc` does not omit it, so `make cov` reports **68%**
> rather than the 93% the attestation core actually achieves. The dashboard is
> demo scaffolding over already-tested modules, but it is untested scaffolding:
> treat its output as a view of the CLI's results, not as independently verified.
> Either write tests for it or add `faceproof/ui/*` to the `.coveragerc` omit
> list with that reasoning recorded — do not simply quote 93% as the project number.

> [!NOTE]
> **Two tests assert POSIX-only file semantics and fail on Windows:**
> `tests/test_consent.py::test_file_permissions_are_owner_only` (POSIX `chmod 0600`, not implemented by Windows Python) and
> `tests/test_manifest.py::test_non_serialisable_values_do_not_crash` (expects a `/tmp/x` path string).
> Both pass on the `ubuntu-latest` CI matrix (Python 3.11 / 3.12 / 3.13).

### Foundry tests

```bash
forge test --root contracts
```

```
Ran 9 tests for test/EvidenceRegistry.t.sol:EvidenceRegistryTest
[PASS] testInitialTotalIsZero()
[PASS] testAnchorSuccessAndTotalProgression()
[PASS] testLookupById()
[PASS] testLookupByRoot()
[PASS] testZeroRootReverts()
[PASS] testDuplicateRootReverts()
[PASS] testUnknownAnchorReverts()
[PASS] testAnchoredEventIsEmitted()
[PASS] testVerifyFieldOnEightLeafTree()
Suite result: ok. 10 passed; 0 failed; 0 skipped
```

### Anvil integration (optional)

With a local node running (`make anvil` in another terminal), `tests/test_chain.py` deploys the registry from the Foundry artifact, anchors a Python-built bundle, and checks that a Python-generated Merkle proof verifies **on chain** via `verifyField()` — the cross-implementation compatibility check.

```
5 passed
```

---

## Project structure

```
.
├── faceproof/
│   ├── config.py           all tunables; prints itself into every run        [Stage 1]
│   ├── manifest.py         append-only JSONL run log                         [Stage 1]
│   ├── face.py             detection, quality gate, ArcFace encoding         [Stage 1]
│   ├── consent.py          consent store, commitments, erasure               [Stage 1]
│   ├── handoff.py          the Stage 1 → Stage 2 boundary artifact           [Stage 1]
│   ├── calibrate.py        threshold measurement                             [Stage 1]
│   ├── cli.py              the recorded Stage 1 surface                      [Stage 1]
│   ├── canonical.py        deterministic JSON, q(), float rejection          [Stage 3]
│   ├── merkle.py           double-keccak leaves, sorted-pair tree, proofs    [Stage 3]
│   ├── bundle.py           the 8 evidence groups, root, proofs, abstain      [Stage 3]
│   ├── stage2_adapter.py   read-only consumer of Stage 2's interface         [Stage 3]
│   ├── stage2_bridge.py    runs Person 2's real fuse/channel_b/index → stage2.json  [integration]
│   ├── chain.py            Web3.py — Anvil + Polygon Amoy, ABI from artifact [Stage 3]
│   ├── anchor.py           anchor the root, write an auditable receipt       [Stage 3]
│   ├── verify.py           independent re-verification, selective disclosure,
│   │                       tamper demonstration                             [Stage 3]
│   └── run.py              Stage 3 CLI: stage2 / search / anchor / verify / tamper /
│                           abstain / forget / deploy / anvil / demo         [Stage 3]
├── contracts/
│   ├── src/EvidenceRegistry.sol    append-only registry + MerkleLite         [Stage 3]
│   ├── test/EvidenceRegistry.t.sol 10 Foundry tests                         [Stage 3]
│   ├── script/Deploy.s.sol         deploy script                            [Stage 3]
│   └── foundry.toml                solc 0.8.24                              [Stage 3]
├── vendor/stage2/          Person 2's Stage 2 branch, vendored             [Stage 2]
├── tests/                  Stage 1 + Stage 3 + test_stage2_bridge, fully mocked
├── application.md          the integrated three-stage architecture
├── scripts/                fixture + artwork generators, self-verifying
└── assets/                 README artwork, light and dark
```

---

## Limitations

- **Channel B is not implemented.** Person 2's `channel_b.discover` is a three-line stub that returns `{"accepted": false, "reason": "no_SERPAPI_KEY_or_ephemeral_host"}` unconditionally — the reason string is misleading, because it is returned **whether or not** `SERPAPI_KEY` is set (a key is present in this checkout and changes nothing). Implementing it would mean uploading a real person's face to a third-party reverse-image API, which contradicts the project's stated privacy posture ("no probe image ever leaves the host"), so it is deliberately left off. Fusion handles the single-channel case correctly and reports `channel_b:no_SERPAPI_KEY_or_ephemeral_host` in `channels_used`.

Stage-3-specific constraints (the pipeline's broader limits are in **[LIMITATIONS.md](LIMITATIONS.md)**):

- **Polygon Amoy anchor is live but singular.** `EvidenceRegistry` is deployed at `0xeE0efb2a3D75f1933f171dE8e8D9Dd14903170d3` and exactly one root (anchor id `0`) has been anchored — a demonstration on the synthetic Stage 2 fixture, not a run over real discovery output. The Amoy code path shares `chain.py` with Anvil; the local Anvil path is still what the integration tests exercise on every commit.
- **The ABI artifact is generated, not committed.** `contracts/out/` is gitignored, so `chain.py` needs `forge build` (or `make deploy`) to run once before any chain operation. Standard for Foundry projects; the Makefile targets and CI handle it.
- **Stage 3 consumes the discovery result through a read-only adapter.** When no Stage 2 result file is present in the run directory, `stage2_adapter` falls back to a **clearly labelled synthetic fixture** (`source: "synthetic-stub"`, `channels_used: ["channel_a:synthetic-stub"]`) so the attestation path is demonstrable in isolation. It is unmistakable in the manifest and the bundle provenance when no real discovery took place.
- **Stage 2 is wired in via `faceproof/stage2_bridge.py`, not a code merge.** Person 2's package is also named `faceproof` with an older, incompatible implementation, so the bridge loads only their dependency-free real functions (`fuse`, `channel_b`, `index.search`) by file path and emits `stage2.json`. This repo ships **no** FAISS corpus/index (it is gitignored — see [`data/index/README.md`](data/index/README.md)), so `stage2` / `search --real-stage2` in a clean clone demonstrates the **genuine abstain** path. Locally the index is built from consenting photographs via `run corpus-local` (see [Channel A corpus](#channel-a-corpus--local-consenting-photographs)), and the **positive-match path is a real search**: a held-out photograph of a consenting subject is matched against a locally-built index, accepted on the measured threshold, and anchored. The corpus is whatever you build with `run corpus-local`; nothing is committed, so the size and composition of your index are yours and the numbers above will differ. The labelled synthetic fixture (`--demo`) remains available for exercising Stage 3 in a clean clone that has no corpus, and is never reached unless that flag is passed. See [`application.md`](application.md).
- **Calibration has been measured, on a small sample.** `data/calibration.json` was produced by `faceproof/calibrate.py` from real consenting photos in `data/calib/<subject_id>/` (the photos are gitignored), and `accept_at = 0.0967` is the value now in force — `config.py` reads the file, so the number cited on camera is the number the gate uses. It rests on **2 subjects / 6 images / 9 impostor pairs**, so the impostor maximum it is derived from is a weak upper bound; treat the threshold as provisional and re-measure with more subjects before drawing any conclusion about accuracy.
- **A live face probe needs the model stack and a one-time download.** `insightface` + `onnxruntime` + a ~330 MB `buffalo_l` fetch (`make setup`) are required for Stage 1 detection, calibration and the Channel A index build. `pyproject.toml` pins **`insightface==0.7.3`**, which is sdist-only and builds from source — fine on macOS/Linux, but on Windows it needs [MSVC C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/). `pip install -e ".[dev]"` installs the tested set. The attestation core and the full Python suite need none of it.
- **Anvil deployment addresses are deterministic and disposable.** Any address or transaction hash shown for a local run comes from a throwaway chain and regenerates on every run.
- **One test asserts POSIX-only file semantics** and fails on Windows: `tests/test_consent.py::TestStore::test_file_permissions_are_owner_only` expects mode `600` after `chmod`, and Windows reports `666`. The consent store is still written 0600-then-replace; only the assertion is unportable. It passes on the Linux CI.

---

## Design rationale

The pipeline's design decisions live in **[DECISIONS.md](DECISIONS.md)**. Stage 3 adds a few of its own:

- **Why the root is recomputed, never trusted** — a verifier that compares against the stored `merkle_root` proves nothing; verification rebuilds every leaf from the group bytes and derives the root itself.
- **Why leaves are double-hashed** — `keccak256(keccak256(x))` domain-separates a leaf from an internal node, so a proof cannot pass off an internal node as a leaf.
- **Why the pair is sorted** — `keccak256(min ‖ max)` lets a proof carry only sibling hashes and makes the Solidity verifier a two-line loop that matches the Python exactly.
- **Why Stage 3 reuses Stage 1's commitment** — recomputing `keccak256(salt ‖ embedding)` in Stage 3 would mean reading the salt and the raw vector; instead the digest already in `probe.json` is carried through untouched.
- **Why an abstain is a first-class output** — an identity system that always produces a match is a liability; `AbstainError` + `abstain.json` make "not enough evidence" a recorded, non-anchoring result.

Ten honest constraints for Stage 1 remain in **[LIMITATIONS.md](LIMITATIONS.md)**.

<sub>Artwork is generated, not hand-drawn: `python scripts/gen_readme_assets.py` rebuilds every SVG in both themes.</sub>

---

<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/footer-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/footer-light.svg">
  <img alt="OneReign — Allen (@asta-maxx), Anbi (@Anbi105), Harley Davis (@harleydavis2)" src="assets/footer-light.svg" width="620">
</picture>

[@asta-maxx](https://github.com/asta-maxx) · [@Anbi105](https://github.com/Anbi105) · [@harleydavis2](https://github.com/harleydavis2)

<sub>Built for the unedited take — every command is a Makefile target, and every stage prints its evidence.</sub>

</div>
