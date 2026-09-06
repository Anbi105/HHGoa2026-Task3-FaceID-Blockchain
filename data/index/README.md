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

## Build it (Person 2's real modules)

```bash
# 1. ingest public posts with images  ->  data/index/raw.jsonl
python -m faceproof.ingest_bsky --handles alice.bsky.social bob.bsky.social

# 2. re-fetch each raw.jsonl image to a local path, then:
#    faceproof.index.build(records, config)   ->  faiss.bin + sidecar.jsonl + snapshot.json
python -m faceproof.index
```

> **Known gap in Person 2's Stage 2:** `faceproof.index.build(records, config)`
> expects each record to carry a `local_image` path (a re-fetched file),
> but `faceproof.ingest_bsky` writes only `image_url`. The fetch step
> between ingest and index is not implemented on the `person2` branch (the
> guide's reference `index.py` does it inline). Supply that fetch step, or
> use the guide's `index.py`, before `build()` will run. This is Person 2's
> to close — it is not patched here.

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
