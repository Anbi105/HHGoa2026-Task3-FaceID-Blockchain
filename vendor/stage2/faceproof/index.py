import hashlib, json
from pathlib import Path
import numpy as np

def snapshot_id(sidecar): return hashlib.sha256(Path(sidecar).read_bytes()).hexdigest()
def build(records, config, out_dir="data/index"):
    import faiss
    from .face import probe_image
    out=Path(out_dir); out.mkdir(parents=True, exist_ok=True); embeddings=[]; side=[]
    for record in records:
        try:
            result=probe_image(record["local_image"], config); embeddings.append(result.embedding); side.append({**record,"face_bbox":result.bbox})
        except Exception as e: print(f"INDEX skipped: {record.get('local_image')} ({e})")
    if not embeddings: raise RuntimeError("no faces indexed — check corpus/network")
    index=faiss.IndexIDMap2(faiss.IndexFlatIP(512)); vectors=np.stack(embeddings); ids=np.arange(len(side),dtype=np.int64); index.add_with_ids(vectors,ids); faiss.write_index(index,str(out/"faiss.bin"))
    (out/"sidecar.jsonl").write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in side),encoding="utf-8")
    summary={"snapshot_id":snapshot_id(out/"sidecar.jsonl"),"n_faces":len(side),"n_images":len({x["local_image"] for x in side}),"n_authors":len({x.get("author_did", "") for x in side}),"model_id":config.model_id}
    (out/"snapshot.json").write_text(json.dumps(summary,indent=2),encoding="utf-8"); return summary
def search(embedding, config, out_dir="data/index"):
    import faiss
    out=Path(out_dir); index=faiss.read_index(str(out/"faiss.bin")); side=[json.loads(x) for x in (out/"sidecar.jsonl").read_text().splitlines()]
    scores,ids=index.search(np.asarray([embedding],dtype=np.float32), min(config.top_k,index.ntotal)); hits=[{**side[int(i)],"score":float(s)} for s,i in zip(scores[0],ids[0]) if i>=0]
    margin=hits[0]["score"]-hits[1]["score"] if len(hits)>1 else 1.0
    accepted=bool(hits and hits[0]["score"]>=config.accept_at and margin>=config.min_margin)
    return {"accepted":accepted,"reason":"accepted" if accepted else ("below_threshold" if not hits or hits[0]["score"]<config.accept_at else "ambiguous_neighbourhood"),"hits":hits,"margin":margin,"snapshot":json.loads((out/"snapshot.json").read_text())}
