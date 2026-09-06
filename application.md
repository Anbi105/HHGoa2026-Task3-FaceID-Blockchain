# Application Context

## Project
Face ID + Blockchain Verification

## Purpose

FaceProof turns a single supplied face image into a **reproducible,
tamper-evident, privacy-preserving attestation on a public blockchain** —
without ever placing raw biometric data on-chain.

It is a three-stage serialized pipeline. Each stage is owned by one team
member, runs on its own, and hands off to the next through a small JSON file
on disk. The file boundary is deliberate: it lets each stage be built and
tested independently, lets a run resume after a mid-pipeline failure, and
proves that Stage 3 could not have influenced Stage 2.

```
Face  →  Social Match  →  On-Chain Attestation
```

| Stage | Owner | Branch | In this repo |
|---|---|---|---|
| 1 — Face Probe | Person 1 | `person-1/stage-1-probe` | `faceproof/{config,manifest,face,consent,handoff,calibrate,cli}.py` (verbatim) |
| 2 — Social Discovery | Person 2 | `person2` | `vendor/stage2/…` (vendored) + `faceproof/stage2_bridge.py` (adapter) |
| 3 — Blockchain Attestation | Person 3 | `person3-blockchain` | `faceproof/{canonical,merkle,bundle,stage2_adapter,chain,anchor,verify,run}.py`, `contracts/` |

## Stage 1 — Face Probe

Entry: `python -m faceproof.cli probe <IMAGE> --subject <SUBJECT>`
(Makefile: `make probe IMAGE=… SUBJECT=…`).

Responsibilities, as implemented by Person 1:

- **Consent.** A consent gate runs *before* the image is read. With no valid
  grant for the subject, no image is loaded, no face is detected, no vector is
  computed (`EXIT_NO_CONSENT`). A grant mints a per-subject 256-bit salt and a
  consent token, stored locally (`data/consent/store.json`, gitignored).
- **Face detection.** InsightFace / SCRFD (`buffalo_l`), largest face selected.
- **Image quality gate**, in order, each reporting the measured value and the
  threshold it missed: detector confidence ≥ `min_det_score`, face size ≥
  `min_face_px`, Laplacian blur variance ≥ `min_blur_var`, and a
  secondary-face ambiguity check (`secondary/primary ≤ max_secondary_face_ratio`).
- **Embedding generation.** ArcFace 512-d, L2-normalised. Written only to a
  local, gitignored `embedding.f32`.
- **Embedding commitment.** `keccak256(salt ‖ embedding)` for the probe;
  `keccak256(consent_token)` for the consent event. The raw vector and token
  never leave the host.
- **Serialized handoff.** `out/run-<id>/probe.json` (schema
  `faceproof.probe.v1`): `status`, `rejection_reason`, `quality`, `quality_gate`
  thresholds, `consent` (opaque `subject_commitment` only), `embedding.commitment`,
  `embedding.sha256`, full `config`. Plus `manifest.jsonl`. Every number is a
  fixed-precision string so bytes reproduce across machines.

## Stage 2 — Social Discovery

Person 2's Stage 2 is a corpus/index search over public social content. It is
reached through a thin adapter, `faceproof/stage2_bridge.py`, which loads
Person 2's `fuse.py`, `channel_b.py` and `index.py` from `vendor/stage2/` by
file path (their package is also named `faceproof`, so it is never placed on
the import path) and never modifies them.

Be precise about what that vendored tree contains: `fuse.fuse` is complete and
is used as-is; `index.search` is complete and is genuine FAISS retrieval; but
`channel_b.discover` is a **three-line stub** that always returns
`{"accepted": False}` (reverse-image search is not implemented on the `person2`
branch, so `SINGLE_CHANNEL_B` is unreachable through the bridge today), and
`index.build` is not reachable through the seam at all — it uses a relative
`from .face import probe_image` that cannot resolve under path-loading, so
corpus building still runs on Person 2's own tree.

Entry: `python -m faceproof.run stage2 --run-dir out/run-<id>`
(or `search … --real-stage2`).

Responsibilities, as implemented by Person 2:

- **Candidate / evidence discovery.**
  - *Corpus ingestion* (`ingest_bsky.py`): seeded ingestion of **public**
    Bluesky (AT Protocol) author feeds for explicitly configured consenting
    handles only, keeping post URI/URL, author DID/handle, text and image URL
    as provenance.
  - *Index build / search* (`index.py`): face embeddings of ingested images are
    stored in a FAISS `IndexIDMap2(IndexFlatIP)` (512-d, inner product) with a
    `sidecar.jsonl` and a `snapshot.json` whose `snapshot_id` is a SHA-256 of
    the sidecar.
- **Channel A** — Person 2's `index.search(embedding, config)`: returns the
  top-k hits with cosine scores, the rank-1 − rank-2 **margin**, and an
  `accepted` flag gated on a calibrated `accept_at` **and** `min_margin`. The
  bridge runs it only when a local index exists under `data/index/`; it never
  fabricates a corpus.
- **Channel B** — Person 2's `channel_b.discover()`: reverse-image search,
  **opt-in**, returns not-accepted unless a SERPAPI key and an ephemeral host
  are configured; it never sends the full probe image.
- **Candidate scoring** is the FAISS cosine score plus the runner-up margin
  (both surfaced in the terminal output and carried into the evidence).
- **Fusion** — Person 2's `fuse.fuse(a, b)`: `CORROBORATED` (both channels
  accepted and their `image_sha256` or `post_uri` agree), `SINGLE_CHANNEL_A`,
  `SINGLE_CHANNEL_B`, or `ABSTAIN`.
- **Explicit abstain.** If neither channel accepts, `fuse` returns `ABSTAIN`
  and the bridge writes `stage2.json` with `fusion_outcome: "ABSTAIN"` and
  `match: null`. Stage 3 then records the abstain and builds no bundle.

Output: `out/run-<id>/stage2.json` (schema `faceproof.stage2.bridge.v1`) —
`fusion_outcome`, `channels_used`, `snapshot_id`, `margin`, `threshold`,
`retrieval_timestamp`, `pipeline_version`, and a `match` block
(`platform`, `post_url`, `post_uri`, `author_did`, `author_handle`,
`text_sha256` + `text_length`, `image_sha256`, `phash`, `source_url`,
`score`). Raw post text is hashed in the bridge and never written to disk.
`image_sha256` / `phash` are left empty when Person 2's corpus does not carry
them (it computes no perceptual hash) — no field is invented.

> This repository ships **no** FAISS corpus/index and Person 2 deliberately did
> not fabricate one. With no index present, Channel A cannot retrieve, Person 2's
> `fuse` returns `ABSTAIN`, and the integrated run demonstrates the genuine
> abstain path. The **positive** match path is demonstrated through Person 3's
> clearly-labelled `stage2_adapter` synthetic fixture (`source: synthetic-stub`),
> which is the project's built-in deterministic fallback.

## Stage 3 — Blockchain Attestation

Entry: `python -m faceproof.run search --run-dir out/run-<id> [--anchor]`,
then `verify [--chain]` and `tamper`.

Responsibilities, as implemented by Person 3:

- **Canonical evidence serialization** (`canonical.py`): deterministic JSON —
  sorted keys, no whitespace, UTF-8 — rejecting bare floats and non-string
  keys; every number is a fixed-precision string via `q()`.
- **Stage 2 adapter** (`stage2_adapter.py`): reads `out/run-<id>/stage2.json`
  (or `discovery.json` / `match.json` / `fuse.json`) and normalises it; falls
  back to a labelled synthetic fixture when no Stage 2 file is present. Raw post
  text is hashed and dropped here too.
- **Evidence bundle** (`bundle.py`): exactly **eight groups, in order** —
  `probe`, `consent`, `match_location`, `match_author`, `match_text`,
  `match_image`, `scores`, `provenance` — each carrying only commitments,
  hashes and metadata. A privacy guard rejects any group that contains an
  embedding, token, raw text or vector-shaped field. Groups 0–1 reuse Stage 1's
  commitments verbatim.
- **Merkle commitment** (`merkle.py`): leaf = `keccak256(keccak256(canon(group)))`;
  internal node = `keccak256(min(a,b) ‖ max(a,b))`; a full binary tree of depth
  3 → one root. Mirrored byte-for-byte by `MerkleLite` in the contract.
- **Blockchain anchor** (`chain.py`, `anchor.py`, `contracts/src/EvidenceRegistry.sol`):
  append-only, ownerless registry — `anchor(root, schema, bundleURI)`; views
  `total` / `get` / `idOf` / `isAnchored` / `verifyField`. `anchor` recomputes
  the root and refuses on mismatch or `ABSTAIN`, then writes `receipt.json`.
  Live target Polygon Amoy (chain id 80002); deterministic offline fallback
  Anvil (31337).
- **Independent re-verification** (`verify.py`): recomputes every leaf and the
  root from the group bytes — it never trusts `bundle["merkle_root"]` — and
  compares against the stored value and, when a receipt exists, the on-chain
  record.
- **Selective disclosure**: one group (`match_location`) can be revealed alone
  and proven under the anchored root via its inclusion proof, locally and
  through the contract's `verifyField`.
- **Tamper detection**: a one-character edit to `match_location.post_url`
  changes that group's bytes, its leaf and the recomputed root, so the anchored
  proof no longer verifies.

Live on Polygon Amoy (from branch `person3-blockchain`):

| | |
|---|---|
| Registry | `0xeE0efb2a3D75f1933f171dE8e8D9Dd14903170d3` |
| Deployment tx | `0xdf7bf97cc2e1661efabfe60e1a367440f5e5119a4df1e15c48c425389785be79` (block 46888484) |
| Anchor id 0 | `0x4365d17c38ea8851ca18f62486b4f7471ab1b8023f9078c672e1c4552ab980b8` (block 46888956) |
| Explorer | https://amoy.polygonscan.com/address/0xeE0efb2a3D75f1933f171dE8e8D9Dd14903170d3 |

## Complete Data Flow

```
probe image
   │  python -m faceproof.cli probe <img> --subject <s>
Stage 1  ── consent gate ─ face detect ─ quality gate ─ ArcFace 512-d ─ commitments
   │
   ▼  out/run-<id>/probe.json      (+ embedding.f32 LOCAL ONLY, manifest.jsonl)
   │
Stage 2  ── faceproof/stage2_bridge.py  (Person 2's real fuse / channel_b / index.search)
   │        Channel A: FAISS top-k + runner-up margin   (only if data/index/ present)
   │        Channel B: opt-in reverse image search
   │        fuse → CORROBORATED | SINGLE_CHANNEL_A | SINGLE_CHANNEL_B | ABSTAIN
   ▼  out/run-<id>/stage2.json      (ABSTAIN ⇒ Stage 3 writes abstain.json, no bundle)
   │
Stage 3  ── stage2_adapter → canonical serialization → 8 evidence groups
   │        → Merkle leaves (double keccak) → Merkle root
   ▼  out/run-<id>/bundle.json + proofs.json
   │
Blockchain  EvidenceRegistry.anchor(root, schema, bundleURI)   [Anvil 31337 | Polygon Amoy 80002]
   ▼  out/run-<id>/receipt.json
   │
Verification  root recomputed from the bundle, checked vs stored value AND on-chain record;
              selective disclosure of match_location proven locally + via verifyField();
              one-character tamper ⇒ recomputed root changes ⇒ verification FAILS / DETECTED
```

## Privacy

Raw biometric and personal data never reaches the chain or the shared bundle:

- The raw 512-d embedding stays in a local gitignored `embedding.f32`; only
  `keccak256(salt ‖ embedding)` moves forward.
- The per-subject salt and consent token stay on the host; only
  `keccak256(consent_token)` is recorded. `make forget` / `faceproof.run forget`
  destroys the salt, making an already-anchored commitment unverifiable while
  leaving the withdrawal auditable.
- Raw post text is hashed (SHA-256 + length) and dropped in the Stage 2 bridge
  and again in `stage2_adapter`; it is never written to `stage2.json`.
- Image bytes are represented only by a SHA-256 (and a perceptual hash where a
  corpus provides one).
- `bundle.verify_bundle_privacy()` rejects any group carrying an embedding,
  token, raw text or vector-shaped field.
- The on-chain record stores only a 32-byte root, a 32-byte schema hash, a
  short URI, the submitter address, and a block timestamp.
- Person 2's Channel B is opt-in and, when enabled, is specified to transmit
  only a tightly cropped face to a short-lived URL and to re-score any
  candidate locally rather than trust a snippet.

## Integration Architecture

One main working project at the repository root, combining three completed
stages through their serialized interfaces — **not** by merging code.

- **Root `faceproof/` package = Stage 1 (Person 1) + Stage 3 (Person 3).** The
  Stage 1 modules are byte-for-byte identical to the `person-1/stage-1-probe`
  branch; the Stage 3 modules and `contracts/` are the `person3-blockchain`
  branch. They already share one `config.py`.
- **Two file-based seams**, unchanged from each owner's design:
  `probe.json` (Stage 1 → Stage 2) and `stage2.json` (Stage 2 → Stage 3).
- **Stage 2 is reached through an adapter, not a rewrite.** Person 2's branch
  is vendored into this repo under `vendor/stage2/` (Person 2
  nested their whole tree there). Their package is *also* named `faceproof`
  with the same module names but an older, incompatible implementation, so it
  cannot be imported alongside the root package. `faceproof/stage2_bridge.py`
  (Person-3-owned, new) therefore loads only Person 2's dependency-free real
  functions — `fuse.fuse`, `channel_b.discover`, `index.search` — by file path
  via `importlib`, runs them, and emits `stage2.json`. No Person 2 file is
  modified; no corpus is fabricated.
- **CLI.** The existing Stage 3 `faceproof.run` surface is extended, not
  replaced: a new `stage2` subcommand and a `--real-stage2` flag on `search` /
  `demo`. Every existing command (`banner`, `index-stats`, `probe`, `search`,
  `anchor`, `verify`, `tamper`, `abstain`, `forget`, `deploy`, `anvil`, `demo`)
  behaves exactly as before when the new flag is absent.
- **Reference clones.** `person1/` and `person2/` are independent full clones of
  the other branches, kept side by side for review. They are untracked and are
  never modified or copied over the root.

### Known gaps (real external inputs required — not fabricated)

- **`data/calibration.json` is absent.** Person 1's `faceproof/calibrate.py`
  generates it from ≥2 subjects × ≥2 images each of real consenting people in
  `data/calib/<subject_id>/` (gitignored, absent — see `data/calib/README.md`).
  Command: `python -m faceproof.calibrate data/calib`. Until it exists the
  pipeline uses the documented `accept_at = 0.55` placeholder with a
  `make config` warning; after it exists, set `FACEPROOF_ACCEPT_AT` to the
  measured `suggested_accept_at` (`config.py` does not auto-read the file).
  Synthetic faces are explicitly rejected for this (impostor cosine ≈ 0.71).
- **No FAISS corpus/index** (`data/index/` — see `data/index/README.md`), by
  Person 2's explicit decision. A real successful Stage 2 match therefore
  cannot run in a clean clone. The **abstain** path is genuine (Person 2's real
  `fuse` returns `ABSTAIN`); the **positive** path uses the labelled
  `stage2_adapter` synthetic fixture. Person 2's `index.build` also needs a
  re-fetch step between `ingest_bsky` and `build` that is not on the `person2`
  branch — noted in `data/index/README.md`, Person 2's to close.
- **`insightface` / `onnxruntime` / `buffalo_l` weights are not in the test
  `.venv`**, so a live Stage 1 face probe and the blurry / group-photo
  quality-gate fixtures (`scripts/make_demo_variants.py`) cannot be produced
  here. The `.venv` runs the full mocked test suite; a live probe needs
  `insightface==0.7.3` + `onnxruntime` + a one-time ~330 MB model download.
- **`requirements.lock.txt` does not match the test `.venv`.** The lock file is
  a Python-3.14 / numpy-2.5.2 / insightface freeze with no web3; the `.venv`
  that passes the suite is Python 3.11-class with numpy 1.26.4 + web3 8.0.0 and
  no insightface. `pip install -e ".[dev]"` (per README) installs the tested
  Stage 1 + Stage 3 set. The two dependency descriptions should be reconciled
  by the team before submission.
