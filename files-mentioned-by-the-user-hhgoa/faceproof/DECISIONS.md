# Decisions

| Decision | Choice | Why | Rejected alternative |
|---|---|---|---|
| Face model | InsightFace buffalo_l / SCRFD / ArcFace | Required detector and 512-D embeddings | dlib/face_recognition |
| Similarity | normalized cosine | Stable inner-product retrieval | unnormalised distance |
| Threshold | measured calibration | avoids invented scores | blog-derived constant |
| Social search | consented Bluesky index | public AT Protocol provenance | Instagram/X scraping |
| Reverse search | SerpAPI-compatible opt-in | independently re-verified locally | trusting snippets |
| Index | FAISS IndexFlatIP | exact cosine search | hardcoded matches |
| Evidence | eight field groups + Merkle | selective disclosure | full bundle on-chain |
| Hash | keccak256 | EVM-compatible | non-EVM hash for root |
| Serialization | canonical JSON | stable bytes | arbitrary json.dumps |
| Networks | Anvil + Polygon Amoy | local reproducibility + public testnet | testnet-only demo |
| Registry | append-only | historical anchors cannot be rewritten | upgradeable proxy |
| Consent | hashed consent commitment | binds scope without exposing record | unbound biometric processing |
| Decisions | explicit abstention | avoids forced top-1 | always returning a person |
| Interface | CLI + JSONL manifest | observable, reproducible stages | unneeded UI |

## Current deviation

Fixtures, prebuilt index, a funded Amoy wallet, deployed registry, and third-party keys are not present in this empty workspace. They are intentionally not fabricated. The source implements their real paths and fails clearly until consenting operational data and credentials are supplied.
