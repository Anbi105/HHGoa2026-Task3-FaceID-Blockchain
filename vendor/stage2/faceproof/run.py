import argparse, json, time
from pathlib import Path
from .config import load_config
from .consent import load_consent, commitment as consent_commitment
from .face import probe_image, FaceError
from .channel_a import discover as channel_a
from .channel_b import discover as channel_b
from .fuse import fuse
from .bundle import create
from .manifest import event
from .verify import main as verify
from .anchor import submit
def main(img):
    config=load_config(); run=Path("out")/f"run-{int(time.time())}"; run.mkdir(parents=True); manifest=run/"manifest.jsonl"; event(manifest,"STAGE 1","probe_loaded",image=img)
    try: probe=probe_image(img,config)
    except FaceError as e: event(manifest,"STAGE 1","REJECT",reason=str(e)); return 2
    event(manifest,"STAGE 1","embedding_ready",dim=512); consent=load_consent(Path("data/consent")/(Path(img).stem+".json")); event(manifest,"STAGE 1","consent_bound")
    a=channel_a(probe.embedding,config); b=channel_b(probe.embedding,config); outcome=fuse(a,b); event(manifest,"FUSION",outcome["outcome"])
    if outcome["outcome"]=="ABSTAIN": return 0
    bundle=create(run,probe.embedding,consent_commitment(consent),outcome,a,config); event(manifest,"ATTESTATION","merkle_root",root=bundle["root"])
    receipt=submit(run,config); event(manifest,"CHAIN","anchor_confirmed",transaction=receipt["transaction_hash"]); verify(run); return 0
if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--img",required=True); raise SystemExit(main(p.parse_args().img))
