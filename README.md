<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/hero-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/hero-light.svg">
  <img alt="FaceProof — consent-gated face identification for on-chain attestation" src="assets/hero-light.svg" width="100%">
</picture>

<br/>

[![tests](https://github.com/Anbi105/HHGoa2026-Task3-FaceID-Blockchain/actions/workflows/tests.yml/badge.svg?branch=person3-blockchain)](https://github.com/Anbi105/HHGoa2026-Task3-FaceID-Blockchain/actions/workflows/tests.yml)
[![coverage](https://img.shields.io/badge/coverage-97%25-3fb950?labelColor=1f2328)](#tests)
[![python tests](https://img.shields.io/badge/pytest-221-3fb950?labelColor=1f2328)](#tests)
[![foundry](https://img.shields.io/badge/forge_test-9%20passing-3fb950?labelColor=1f2328)](#foundry-tests)
[![solidity](https://img.shields.io/badge/solidity-0.8.24-363636?logo=solidity&logoColor=white&labelColor=1f2328)](contracts/src/EvidenceRegistry.sol)
[![python](https://img.shields.io/badge/python-3.11%20|%203.12%20|%203.13-3776AB?logo=python&logoColor=white&labelColor=1f2328)](pyproject.toml)
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

| Stage | Job | Modules | Owner | Status |
|:-----:|-----|---------|-------|--------|
| **1** | **Probe** — detect, gate, encode, consent-bind → write the handoff | `config` `manifest` `face` `consent` `handoff` `calibrate` `cli` | Person 1 | ✅ complete · calibration data pending |
| **2** | **Discovery** — social index + reverse-image search → a match or an abstain | Person 2, branch `origin/person2` | Person 2 | ⬜ in progress (separate branch) |
| **3** | **Attestation** — canonicalise, commit, Merkle, anchor, re-verify | `canonical` `merkle` `bundle` `stage2_adapter` `chain` `anchor` `verify` `run` + `contracts/` | Person 3 | ✅ complete |

Stage 3 takes the evidence the earlier stages produced and turns it into a **reproducible, tamper-evident cryptographic attestation**: eight canonical evidence groups → eight Merkle leaves → one root → one on-chain record. Anyone can later recompute the root from the bundle and check it against the chain.

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

```bash
git clone -b person3-blockchain https://github.com/Anbi105/HHGoa2026-Task3-FaceID-Blockchain.git
cd HHGoa2026-Task3-FaceID-Blockchain
python -m venv .venv
```

**Windows (PowerShell or Git Bash)** — activation is unreliable, so call the interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

**Linux / macOS / WSL:**

```bash
source .venv/bin/activate && pip install -e ".[dev]"
```

Installing the package pulls in the Stage 3 dependencies (`web3`, `eth-utils`) alongside Person 1's pinned stack. For the smart-contract half you also need [Foundry](https://getfoundry.sh) (`forge`, `anvil`) on your `PATH`.

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
| `make search` | `search` | Stage 1 handoff → Stage 2 result → 8-group evidence bundle |
| `make anchor` | `anchor` | Anchor the latest run's Merkle root on-chain |
| `make verify` | `verify` | Independently re-verify the latest run (`CHAIN=1` adds on-chain checks) |
| `make tamper` | `tamper` | Single-character tamper demonstration |
| `make abstain` | `abstain` | Show the abstain path (quality-gate rejection → no bundle) |
| `make forget` | `forget` | Revoke consent and destroy the erasure salt |
| `make deploy` | — | `forge build` + deploy `EvidenceRegistry` to local Anvil |
| `make anvil` | — | Start a local Anvil node on `:8545` |
| `make forge-test` | — | Run the Foundry contract test suite |
| `make stage3-test` | — | Run only the Stage 3 Python tests |

Windows equivalent, e.g.: `.\.venv\Scripts\python.exe -m faceproof.run search --img data\demo\synthetic_face.jpg --subject alice`

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

## Calibration

> [!CAUTION]
> **Not yet measured.** `accept_at = 0.55` is the guide's placeholder, not a result. `make config` prints a warning while `data/calibration.json` is absent, so the recording cannot accidentally imply otherwise.

```
data/calib/<subject_id>/*.jpg      # 2+ subjects, 5–10 images each, varied lighting and angle
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
  "merkle_root": "0xbd9643d34189af122492472303311cf2bac38066d9c00b98906a91ad69a0d8fc",
  "groups": {
    "probe":    { "commitment": "0x…", "model_id": "…", "det_score": "0.960000", "blur_var": "72.500000" },
    "consent":  { "subject_ref": "0x…", "commitment": "0x…", "granted_at": "…", "scope": "face_probe_demo" },
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
| `contracts/test/EvidenceRegistry.t.sol` | 9 Foundry tests (no `forge-std` dependency — a minimal `Vm` interface is declared locally) |
| `contracts/script/Deploy.s.sol` | `DeployScript.run()` — deploys the registry inside a broadcast |
| `contracts/foundry.toml` | `solc_version = "0.8.24"`, `src/test/script/out` layout, `[rpc_endpoints]` for `anvil` and `amoy` |

</details>

### 7 · Networks — `faceproof/chain.py`

| Network | Chain ID | RPC | Notes |
|---------|:--------:|-----|-------|
| **Anvil** (local) | `31337` | `http://127.0.0.1:8545` | default; used by the integration tests and the offline demo |
| **Polygon Amoy** | `80002` | `https://rpc-amoy.polygon.technology` | proof-of-stake → the POA extra-data middleware is injected automatically |

- **RPC config** — `CHAIN` selects `anvil` / `amoy`; `RPC_URL` overrides the endpoint; 30-second HTTP timeout.
- **ABI loading** — strictly from the Foundry build artifact `contracts/out/EvidenceRegistry.sol/EvidenceRegistry.json`. Run `forge build` (or `make deploy`) first; a clear error is raised if the artifact is missing. No hand-maintained ABI.
- **Keys & addresses** — `PRIVATE_KEY` and `REGISTRY_ADDRESS` are read from the environment (`Account.from_key`); nothing sensitive is hard-coded or logged. The only literal key in the repo is the world-known public Anvil dev account, used solely by `make deploy` and the local tests.
- **What goes on chain** — a 32-byte root, a 32-byte schema hash, and a short URI string. Never an embedding, an image, a token, or text.

> [!NOTE]
> **Amoy support is implemented but not yet fired live.** Anchoring to Amoy needs a funded testnet account; this repository contains **no** deployed Amoy address, transaction, or explorer link. The Anvil path exercises the identical `chain.py` code.

### 8 · The transaction receipt

`make anchor` recomputes the root from the bundle, refuses if it disagrees with the stored value or if the fusion verdict is `ABSTAIN`, sends `anchor()`, then writes:

```jsonc
// out/run-<id>/receipt.json  — local Anvil (chain id 31337), a throwaway chain:
// every address / hash regenerates on each run.
{
  "anchor_id": 0,
  "chain": "anvil",
  "chain_id": 31337,
  "contract": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
  "root": "0xbd9643d34189af122492472303311cf2bac38066d9c00b98906a91ad69a0d8fc",
  "schema": "faceproof.evidence.v1",
  "bundle_uri": "",
  "submitter": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
  "tx_hash": "0x8cb70344706c7016c3f43ed729170785f599a530a551f8e35ff85e9715673b5a",
  "block_number": 2,
  "gas_used": 163419,
  "status": 1,
  "explorer_url": null
}
```

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
  selective disclosure (regenerated proof) | match_location         | PASS
  selective disclosure (proofs.json)       | match_location         | PASS
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

## Tests

### Full suite

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

```
215 passed, 4 skipped, 2 failed
```

| Bucket | Count | Notes |
|--------|:-----:|-------|
| Stage 1 (Person 1) | 167 | detection, gate, consent, handoff, manifest, calibrate, CLI, golden vectors — unchanged |
| Stage 3 Python (Person 3) | 54 | `test_canonical` 8 · `test_merkle` 11 · `test_bundle` 11 · `test_stage2_adapter` 5 · `test_verify` 7 · `test_run` 7 · `test_chain` 5 |
| Skipped locally | 4 | `test_chain.py` cases that need a running Anvil node |
| Coverage | **97%** | `chain.py` / `anchor.py` (live-RPC glue) omitted via `.coveragerc`; everything else measured |

> [!NOTE]
> **Two Stage 1 tests fail on Windows only** and are **not** caused by Stage 3:
> `tests/test_consent.py::test_file_permissions_are_owner_only` (asserts POSIX `chmod 0600`, which Windows Python does not implement) and
> `tests/test_manifest.py::test_non_serialisable_values_do_not_crash` (asserts a POSIX `/tmp/x` path string).
> Both pass on the project's `ubuntu-latest` CI matrix (Python 3.11 / 3.12 / 3.13), and both fail identically on a pristine checkout with none of the Stage 3 work applied. Person 1's implementation and tests were **not** modified to hide them.

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
Suite result: ok. 9 passed; 0 failed; 0 skipped
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
│   ├── chain.py            Web3.py — Anvil + Polygon Amoy, ABI from artifact [Stage 3]
│   ├── anchor.py           anchor the root, write an auditable receipt       [Stage 3]
│   ├── verify.py           independent re-verification, selective disclosure,
│   │                       tamper demonstration                             [Stage 3]
│   └── run.py              Stage 3 CLI: search / anchor / verify / tamper /
│                           abstain / forget / deploy / anvil / demo         [Stage 3]
├── contracts/
│   ├── src/EvidenceRegistry.sol    append-only registry + MerkleLite         [Stage 3]
│   ├── test/EvidenceRegistry.t.sol 9 Foundry tests                          [Stage 3]
│   ├── script/Deploy.s.sol         deploy script                            [Stage 3]
│   └── foundry.toml                solc 0.8.24                              [Stage 3]
├── tests/                  221 tests — Stage 1 (167) + Stage 3 (54), fully mocked
├── scripts/                fixture + artwork generators, self-verifying
└── assets/                 README artwork, light and dark
```

---

## Limitations

Stage-3-specific constraints (Stage 1's own limits are in **[LIMITATIONS.md](LIMITATIONS.md)**):

- **No live Polygon Amoy anchor.** The Amoy code path is complete and shares `chain.py` with Anvil, but firing it needs a funded testnet account. There is no deployed Amoy address in this repo.
- **The ABI artifact is generated, not committed.** `contracts/out/` is gitignored, so `chain.py` needs `forge build` (or `make deploy`) to run once before any chain operation. Standard for Foundry projects; the Makefile targets and CI handle it.
- **Stage 2 is on a separate branch.** When no Stage 2 result file is present in the run directory, `stage2_adapter` falls back to a **clearly labelled synthetic fixture** (`source: "synthetic-stub"`, `channels_used: ["channel_a:synthetic-stub"]`) so the pipeline is demonstrable end-to-end. It is unmistakable in the manifest and the bundle provenance that no real discovery took place.
- **Anvil deployment addresses are deterministic and disposable.** Any address or transaction hash shown here comes from a local throwaway chain and regenerates on every run.
- **Two Windows-only Stage 1 test failures** (see [Tests](#tests)) — pre-existing, green on Linux CI, untouched by Stage 3.

---

## Design rationale

Person 1's nineteen decisions live in **[DECISIONS.md](DECISIONS.md)**. Stage 3 adds a few of its own:

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
