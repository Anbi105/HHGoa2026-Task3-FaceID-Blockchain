import json
from pathlib import Path
from .bundle import GROUPS
from .merkle import MerkleTree, verify, hex0
def local_verify(run_dir):
    run=Path(run_dir); bundle=json.loads((run/"bundle.json").read_text()); tree=MerkleTree([bundle["fields"][x] for x in GROUPS]); root=hex0(tree.root)
    proofs=json.loads((run/"proofs.json").read_text()); first=GROUPS[0]; proof=proofs[first]
    proof_ok=verify(bytes.fromhex(proof["leaf"][2:]),[bytes.fromhex(x[2:]) for x in proof["proof"]],tree.root)
    return {"root":root,"stored_root":bundle["root"],"root_match":root==bundle["root"],"field_proof":proof_ok}
def main(run):
    r=local_verify(run); chain_match=None
    receipt=Path(run)/"receipt.json"
    if receipt.exists():
        from .config import load_config
        from .chain import anchored_root
        cfg=load_config(); chain_root=anchored_root(cfg.rpc_url,cfg.registry_address,r["stored_root"]); chain_match=(r["root"]==chain_root)
        print(f"local_root = {r['root']}\nchain_root = {chain_root}\nroot_match = {'PASS' if chain_match else 'FAIL'}")
    else: print(f"local_root = {r['root']}\nstored_root = {r['stored_root']}\nroot_match = {'PASS' if r['root_match'] else 'FAIL'}")
    print(f"field_proof = {'PASS' if r['field_proof'] else 'FAIL'}")
    passed=(chain_match if chain_match is not None else r["root_match"]) and r["field_proof"]
    print("VERIFICATION PASS" if passed else "VERIFICATION FAILED")
