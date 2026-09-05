# Decision log — Stage 1 (probe)

The guide's decision log (§3) covers all fourteen pipeline decisions. This
file records **D1–D3, D12–D14 as they were actually implemented in Stage 1**,
plus the choices made inside this component that the guide left open.

A judge who asks "why?" is giving you points to win. Every row is an answer
you should be able to give in one sentence without looking it up.

## From the guide

| # | Decision | Choice | Why | Rejected |
|---|---|---|---|---|
| D1 | Face model | InsightFace `buffalo_l` (SCRFD + ArcFace R50, 512-d) | Current-generation accuracy, ONNX, CPU-viable, well-calibrated cosine space | `face_recognition`/dlib — 128-d, decade-old, materially worse on South Asian faces |
| D2 | Similarity metric | Cosine on L2-normalised embeddings | ArcFace is trained with an angular margin; cosine is the metric it was optimised for | Euclidean L2 — thresholds less interpretable and less portable |
| D3 | Threshold | Calibrated on our own held-out pairs | A number you measured is defensible; a number you copied is not | Hardcoding 0.5 because a blog said so |
| D12 | Consent | Subject token bound into the record; face hash salted per subject | Makes this a verification system, not a de-anonymiser; salt destruction is an erasure path against an immutable chain | Open-world search over arbitrary faces — the Clearview posture, and a DPDP Act problem in India |
| D13 | Abstention | Explicit third outcome, exit code 1, its own handoff record | A system that always returns a match is a system with no precision | Always returning top-1 |
| D14 | Orchestration | Plain CLI + JSON manifest between stages | Every stage independently runnable and resumable; the manifest is what you screen-record | A web UI |

## Stage 1 implementation decisions

| # | Decision | Choice | Why | Rejected |
|---|---|---|---|---|
| S1 | Consent enforcement point | Before `cv2.imread`, before detection | If consent is checked after encoding, a biometric has already been computed for someone who did not agree. The refusal path must be provably inert — there is a test asserting the detector is never called. | Printing a `consent=VALID` line and continuing regardless, which is decoration, not a control |
| S2 | Consent storage | Local JSON at `data/consent/store.json`, mode 600, gitignored | It holds tokens and salts. Those are the secrets that make the commitments meaningful; publishing them would defeat the design | Committing the store; keeping consent in memory only (no erasure path, no audit trail) |
| S3 | Erasure mechanism | Revocation destroys the per-subject salt but retains the record | Once the salt is gone, reproducing an anchored `keccak256(salt‖embedding)` requires guessing 256 bits. The retained record keeps the withdrawal auditable | Deleting the record outright — no audit trail; "deleting" from the chain — impossible |
| S4 | Subject leaf | `keccak256(consent_token)` where the token is a random UUID4 | The leaf commits to *a consent event*, not to a person. Two grants to the same subject produce unrelated commitments | Hashing the subject id — a 32-byte digest of a short string is trivially brute-forced, and would put a de-anonymisable identifier on chain |
| S5 | Embedding encoding | `<f4` (little-endian float32), C-contiguous, explicit | Host byte order must not change the commitment. §14 lists "different roots on two machines" as a failure mode; this closes one cause of it | `.tobytes()` on whatever array arrives — native order, possibly non-contiguous |
| S6 | Rejection type | `Rejection(str)` carrying a `.metrics` dict | The CLI can print the numbers that caused a rejection without re-running the detector. Subclassing `str` keeps `==`, `startswith` and f-strings working for Stage 2 | Returning a plain string (forces a second detection pass, which can report different numbers than the ones that rejected); returning a dataclass (breaks every existing caller) |
| S7 | Rejection message content | Value **and** threshold: `image_too_blurry:3.9<45.0` | On video the viewer must see what gate was missed, not just a number they have to look up | `image_too_blurry:3.9` |
| S8 | Stage boundary | `out/run-<id>/{probe.json, embedding.f32, manifest.jsonl}` | §2: the serialised artifact is what lets each stage run alone and proves Stage 3 could not have influenced Stage 2. The raw vector is a separate file so `probe.json` stays safe to show on camera | Passing Python objects in-process — no resume, no evidence, nothing to record |
| S9 | Numbers in `probe.json` | Every one pre-formatted by `q()` into a fixed-precision string; `_reject_floats` raises if any survive | D9. Float repr differences across machines silently break every proof downstream | `json.dumps` defaults |
| S10 | Abstain still writes a record | A rejected probe produces `probe.json` with `status: rejected` | The abstain is evidence, and Stage 2 needs to distinguish "not run" from "ran and declined" | Writing nothing on rejection |
| S11 | Fixture honesty | The generator verifies each fixture against the real detector and fails loudly | An earlier version silently shipped undetectable images, and the working demo depended on JPEG compression artifacts | Trusting that a drawing is detectable because it was last week |
| S12 | No synthetic calibration | `data/calib/` requires real consenting subjects; `make calibrate` errors until they exist | Measured: impostor cosine between *different* synthetic faces is ≈0.71, far above any usable threshold. A number measured on drawings would look like evidence and be worthless | Shipping a `calibration.json` generated from fixtures |
| S13 | Test isolation | An autouse fixture repoints `data_dir`/`out_dir` at `tmp_path` | Without it a test run reads and writes a developer's real consent store | Letting tests touch the real `data/` |
