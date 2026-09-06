# Known limitations

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

---

# Stage 2 — discovery

## 11. There is no corpus in this repository

`data/index/` ships empty. Channel A is genuine FAISS retrieval, but with no
`faiss.bin` / `sidecar.jsonl` / `snapshot.json` it cannot retrieve anything,
so Person 2's fusion returns `ABSTAIN` and Stage 3 records the abstain. That
abstain is real, not staged — but it also means **no positive match has ever
been produced by a real search in this repo.** Building the corpus needs
consenting Bluesky handles, network access and the InsightFace model stack;
see `data/index/README.md` for the exact procedure.

## 12. Channel B is a stub, not an integration

`vendor/stage2/faceproof/channel_b.py` is three lines that always return
`{"accepted": False}`. Reverse-image search was never implemented on the
`person2` branch. Consequences: the `SINGLE_CHANNEL_B` fusion outcome is
unreachable in practice, and `CORROBORATED` — which needs both channels to
agree — is unreachable too. Every outcome the integrated pipeline can
currently produce is `SINGLE_CHANNEL_A` or `ABSTAIN`. The corroboration
security argument in the design is therefore a property of the design, not a
property of the running system.

## 13. Index building does not run through the bridge

`faceproof/stage2_bridge.py` loads Person 2's modules by file path.
`index.build()` uses a relative `from .face import probe_image`, which cannot
resolve that way, so only `index.search` is reachable through the seam.
Corpus construction has to run inside Person 2's own tree.

## 14. The synthetic Stage 2 fixture describes a positive match

When no Stage 2 result exists, `stage2_adapter` can return a fabricated
`SINGLE_CHANNEL_A` record whose bundle is anchorable. It is labelled in the
evidence (`source: "synthetic-stub"`, `channels_used: ["channel_a:synthetic-stub"]`)
and, since the audit, it is **opt-in**: reaching it requires `--demo`, and the
run prints a warning when it is used. Without the flag a missing Stage 2
result is an error, not a silent fabrication.

---

# Stage 3 — attestation

## 15. The chain attests the record, not the truth of the match

Anchoring proves an evidence bundle existed in exactly this form at that
block time and has not changed since. It says nothing about whether the face
match was correct. Conflating the two misreads the system.

## 16. Anchoring is permissionless, and a root can be claimed once

`EvidenceRegistry.anchor` has no access control, and a given root can be
anchored exactly once, forever. Roots are a deterministic function of the
bundle, so an observer who sees your bundle before you anchor can anchor that
root first: your own transaction then reverts `RootAlreadyAnchored`, and the
`submitter` recorded on chain is theirs, not yours. Nothing is forged — the
evidence is still the evidence — but first-anchor is not proof of authorship.
Binding authorship would need a signature over the root from a key committed
in the bundle; that is not implemented.

## 17. The deployed Amoy contract lags the source

The registry at `0xeE0efb2a3D75f1933f171dE8e8D9Dd14903170d3` was deployed
before two audit fixes: `verifyField`'s `proof.length == 3` guard, and the
consent-group change that altered the bundle root. The live anchor (id `0`)
is therefore reproducible only against the pre-fix schema, and the on-chain
proof-length guarantee is not live until a redeploy. The Anvil path always
runs the current source.

## 18. Off-chain availability is not guaranteed

The chain holds a root; the bundle lives locally or at the bundle URI. Lose
it and the anchor is unopenable — deliberately, since that is also the
erasure mechanism.

## 19. Testnet, therefore no economic security

Amoy is not economically secured. The design carries to mainnet unchanged,
but the demonstration does not inherit mainnet finality.

## 20. Anchoring is a public act

The submitting address and the block timestamp are visible forever. The
commitments reveal nothing, but the fact that a run happened is public
metadata.
