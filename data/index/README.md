# Stage 2 corpus / FAISS index

Channel A (guide §6, D4/D6) searches the probe against a **self-built face
index over public social posts**. That index is:

```
data/index/
├── raw.jsonl        ingested public-post records (post URI/URL, author, image URL, text)
├── faiss.bin        FAISS IndexIDMap2(IndexFlatIP), 512-d — one row per detected face
├── sidecar.jsonl    provenance for each indexed face
└── snapshot.json    { snapshot_id (sha256 of sidecar), n_faces, n_images, n_authors, model_id }
```

This directory is **intentionally empty in the repository.** It holds
re-fetched images of real people and is gitignored. The guide is explicit:
the corpus must be built from **public posts by consenting handles** (your
teammates plus public accounts you choose), never scraped or fabricated.

## What you must provide

1. `insightface==0.7.3` + `onnxruntime` installed and the `buffalo_l`
   weights cached (`~/.insightface/models/`, ~330 MB) — the same model
   Stage 1 uses. The test `.venv` in this checkout does **not** have these.
2. `faiss` (present in the test `.venv` as `faiss-cpu`).
3. Network access to the public Bluesky AppView (no key required).
4. A list of consenting Bluesky handles.

> **The fetch step is now implemented** (integration-side, additive).
> `faceproof.index.build(records, config)` requires each record to carry a
> `local_image` path, but `faceproof.ingest_bsky` only records an `image_url` --
> nothing on the `person2` branch downloaded it, so `build` could never run.
> `faceproof/stage2_corpus.py` supplies exactly that step and nothing else:
> ingestion stays Person 2's `ingest_bsky.ingest`, and detection/embedding/FAISS
> stay Person 2's `index.build`. It also loads their tree as a real package so
> their own `from .face import probe_image` resolves.
>
> Each fetched row gains `local_image`, `image_sha256`, `image_phash` and
> `text_sha256` -- the evidence fields the Stage 3 bundle has slots for. Images
> that fail to download are counted and skipped, never replaced with
> placeholder data.

## Build it (one command)

```bash
python -m faceproof.run corpus --handles alice.bsky.social bob.bsky.social
```

That runs ingest -> fetch -> index and prints the snapshot. To rebuild from an
existing `raw.jsonl` without re-ingesting:

```bash
python -m faceproof.run corpus --skip-ingest
```

`--limit N` caps how many images are fetched and indexed.

## After the index exists

`faceproof/stage2_bridge.py` picks it up automatically: with
`data/index/{faiss.bin,sidecar.jsonl,snapshot.json}` present,
`python -m faceproof.run stage2 --run-dir out/run-<id>` runs Person 2's real
`index.search` (real top-k, real rank-1 − rank-2 margin) and Person 2's real
`fuse`, and writes `stage2.json` for Stage 3.

Until then, `stage2` / `search --real-stage2` exercises the **genuine
ABSTAIN** path — Person 2's `fuse` returns `ABSTAIN` because neither channel
can clear its gate. Nothing is faked.

## Why not a synthetic corpus

A hand-built or generated corpus would make the "genuine search" claim
unverifiable and is explicitly rejected by the guide (§1, D4). The abstain
demo on an empty corpus is honest; a fabricated positive match is not.
