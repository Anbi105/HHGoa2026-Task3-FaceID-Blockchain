import os, json, hashlib
from pathlib import Path
from eth_utils import keccak
from .canonical import canonical_bytes
from .merkle import MerkleTree, hex0

GROUPS=("face_commitment","consent_commitment","match_location","provenance","text_commitment","image_commitment","scores","index_run_provenance")
def commitment(embedding, salt): return "0x"+keccak(embedding.astype("float32").tobytes()+salt).hex()
def sha256_text(value): return "0x"+hashlib.sha256(value.encode()).hexdigest()
def create(run_dir, embedding, consent_commitment, fusion, channel_a, config):
    run=Path(run_dir); run.mkdir(parents=True,exist_ok=True); salt=os.urandom(32); (run/"salt.key").write_bytes(salt)
    winner=(channel_a.get("hits") or [{}])[0]
    fields={
      "face_commitment":{"value":commitment(embedding,salt)}, "consent_commitment":{"value":consent_commitment},
      "match_location":{"post_uri":winner.get("post_uri",""),"post_url":winner.get("post_url","")},
      "provenance":{"author_did":winner.get("author_did",""),"author_handle":winner.get("author_handle","")},
      "text_commitment":{"sha256":sha256_text(winner.get("text",""))}, "image_commitment":{"sha256":winner.get("image_sha256","")},
      "scores":{"channel_a_score":f"{winner.get('score',0):.6f}","margin":f"{channel_a.get('margin',0):.6f}","accept_at":f"{config.accept_at:.6f}"},
      "index_run_provenance":{"snapshot_id":channel_a.get("snapshot",{}).get("snapshot_id",""),"fusion":fusion["outcome"],"pipeline_version":config.pipeline_version}
    }
    tree=MerkleTree([fields[x] for x in GROUPS]); bundle={"schema_id":config.schema_id,"fields":fields,"root":hex0(tree.root)}
    (run/"bundle.json").write_bytes(canonical_bytes(bundle))
    proofs={name:{"value":fields[name],"leaf":hex0(tree.leaves[i]),"proof":[hex0(x) for x in tree.proof(i)]} for i,name in enumerate(GROUPS)}
    (run/"proofs.json").write_text(json.dumps(proofs,indent=2),encoding="utf-8"); return bundle
