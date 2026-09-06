import json
from pathlib import Path
from .chain import anchor
def submit(run, config, bundle_uri=""):
    if not config.registry_address or not config.private_key:
        raise RuntimeError("registry address and private key are required to anchor; configure .env (secrets are never printed)")
    receipt=anchor(config.rpc_url,config.registry_address,config.private_key,json.loads((Path(run)/"bundle.json").read_text())["root"],config.schema_id,bundle_uri)
    safe={"transaction_hash":receipt["transactionHash"].hex(),"block_number":receipt["blockNumber"],"chain":config.chain,"contract":config.registry_address}
    (Path(run)/"receipt.json").write_text(json.dumps(safe,indent=2),encoding="utf-8"); return safe
