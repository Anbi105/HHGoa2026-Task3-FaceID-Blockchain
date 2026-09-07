# Local consenting corpus (Channel A)

Channel A searches a **self-built face index**. The guide's reference corpus is
public Bluesky posts, but no member of this team has a Bluesky account and the
public CDN returned HTTP 504 on the one seeded ingest that ran. Rather than
fabricate accounts, posts or embeddings, the demo builds the *same* index from
**real photographs supplied with consent**.

## Layout

```
data/corpus/
    <subject>/          one directory per consenting subject; the name is the label
        photo1.jpg
        photo2.jpg
```

Any of `.jpg .jpeg .png .webp .bmp` is accepted. Directories are the subject
identity — there is no filename matching anywhere in the pipeline.

**These photographs are gitignored** (`data/corpus/*/`). Only this README is
committed. Never add photographs of anyone who has not consented.

## Hold out the probe

The probe must be a **different photograph** of the target, otherwise a match
is a byte-identical self-lookup and proves nothing about recognition:

```
data/probe/target_probe.jpg      # gitignored
```

Either keep the probe outside `data/corpus/`, or hold it out explicitly:

```bash
python -m faceproof.run corpus-local --root data/corpus \
    --exclude data/corpus/alice/photo1.jpg
```

`faceproof.local_corpus.probe_is_in_index()` re-checks this at search time by
image SHA-256, and the run is flagged if the probe file is itself indexed.

## Build

```bash
python -m faceproof.run corpus-local --root data/corpus
python -m faceproof.run index-stats
```

`corpus-local` only produces records. Detection, quality, ArcFace embedding,
L2 normalisation, FAISS `IndexIDMap2(IndexFlatIP(512))`, the sidecar and the
snapshot are all Person 2's unmodified `face.probe_image` / `index.build`.
An image in which InsightFace finds no face is skipped and counted — the gap
between `n_images` and `n_faces` is reported, never hidden.

## Provenance is recorded honestly

A bundle built from this corpus never claims a social-media origin:

| field | value |
|---|---|
| `platform` | `local-consenting-corpus` |
| `source_type` | `local-consenting-corpus` |
| `author_did` | `did:local:<subject>` |
| `post_url` / `post_uri` | `local://corpus/<subject>/<filename>` |
| `text_sha256` | SHA-256 of the empty string (there is no post text) |
