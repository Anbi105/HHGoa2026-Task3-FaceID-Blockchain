# FaceProof

FaceProof is a consent-bound face-verification pipeline: it detects and quality-gates a supplied face, searches a self-built public-content vector index, then commits only privacy-preserving evidence hashes to an append-only registry. It is not an open-world identity system.

Run locally after placing consented fixture images and a seeded index in the expected directories:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
anvil
forge script contracts/script/Deploy.s.sol --rpc-url http://127.0.0.1:8545 --broadcast
make run IMG=fixtures/subject_a.jpg
```

Chain: local Anvil (31337) by default; Polygon Amoy (80002) is supported when explicitly configured. No contract address or transaction is claimed here because none has been deployed from this workspace.

## Privacy

Raw images, embeddings, consent tokens, text, API keys, and private keys never go on-chain. The registry receives only a Merkle root, schema string, URI, submitter, and timestamp. Each run uses a new 256-bit local salt. `make forget RUN=out/run-...` removes the salt and sensitive local evidence but cannot delete an immutable chain anchor.

Channel B is intentionally opt-in. Its production integration must upload only a tightly cropped face to a short-lived URL, disclose that transmission, re-fetch any candidate, and locally re-score it; it must never treat a search snippet as proof.

## Data preparation

Fixtures are deliberately not distributed: operators must use only images of consenting people. Create `data/calib/<subject_id>/` with at least two images for each of at least two subjects, then run calibration. Seed public Bluesky records using only consented configured accounts:

```powershell
python -m faceproof.ingest_bsky --handles consenting-a.bsky.social consenting-b.bsky.social
```

Download/re-fetch the resulting images into a local consented corpus and pass records containing `local_image` to `faceproof.index.build`; embeddings are then created by InsightFace/SCRFD and stored in FAISS `IndexIDMap2(IndexFlatIP)`. This is genuine vector retrieval, not a lookup table.

## Commands

`make probe`, `make search`, `make run`, `make verify RUN=...`, `make tamper RUN=...`, `make abstain IMG=fixtures/unknown.jpg`, and `make forget RUN=...` provide the demo flow. `make tamper` modifies exactly the post URL in the local bundle; verification recalculates the Merkle root and fails cryptographically.

Run Python checks with `make test` and Solidity checks with `cd contracts; forge test -vv`. Toolchains are not installed in this workspace, so no test result has been asserted without actually running it.

## Limitations

Accuracy depends on image quality and model limitations; calibration is only as representative as its consenting dataset. The social corpus is incomplete, and Channel B depends on third-party availability and sends a cropped face externally when enabled. A chain anchor proves evidence integrity, not objective identity truth. See [LIMITATIONS.md](LIMITATIONS.md).
