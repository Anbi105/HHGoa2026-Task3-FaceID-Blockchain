"""Anchor a bundle's Merkle root on-chain and record an auditable receipt (S20).

Flow:

1. load ``bundle.json`` from the run directory;
2. **recompute** the root from the groups (ignoring the stored value) and
   refuse if it disagrees - you never anchor a number you did not derive;
3. refuse if the run is an abstain (no bundle, or fusion verdict ABSTAIN);
4. connect (Anvil or Polygon Amoy), call ``anchor(root, schema, bundleURI)``;
5. write ``receipt.json`` - chain id, contract address, anchor id, tx hash,
   block, gas - and log the same to ``manifest.jsonl``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from rich.console import Console

from faceproof.bundle import BUNDLE_FILENAME, recompute_root
from faceproof.chain import (
    CHAINS,
    anchor_root,
    chain_name,
    get_w3,
    private_key,
    registry_address,
    rpc_url,
)
from faceproof.manifest import Manifest

console = Console()
RECEIPT_FILENAME = "receipt.json"


def anchor(
    run_dir: Path | str,
    *,
    bundle_uri: str = "",
    address: Optional[str] = None,
    priv_key: Optional[str] = None,
    rpc: Optional[str] = None,
) -> Dict[str, Any]:
    """Anchor the bundle in ``run_dir``; return the receipt record it writes."""
    run_path = Path(run_dir)
    bundle_path = run_path / BUNDLE_FILENAME
    if not bundle_path.exists():
        raise FileNotFoundError(
            f"{bundle_path} not found - nothing to anchor (an abstaining run "
            f"has no bundle)"
        )

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    stored_root = bundle.get("merkle_root", "")
    local_root = recompute_root(bundle)
    if local_root.lower() != stored_root.lower():
        raise ValueError(
            f"refusing to anchor: recomputed root {local_root} != stored "
            f"{stored_root}"
        )

    verdict = bundle.get("groups", {}).get("scores", {}).get("fusion_verdict", "")
    if verdict.upper() == "ABSTAIN":
        raise ValueError("refusing to anchor: fusion verdict is ABSTAIN")

    schema = bundle.get("schema_id", "faceproof.evidence.v1")
    name = chain_name()
    addr = address or registry_address()
    key = priv_key or private_key()
    endpoint = rpc or rpc_url(name)

    manifest = Manifest(run_path)
    manifest.log(
        "STAGE 3", "anchoring", chain=name, root=local_root[:12] + "...", registry=addr
    )

    w3 = get_w3(endpoint, name=name)
    if not w3.is_connected():
        raise ConnectionError(f"cannot reach {name} RPC at {endpoint}")

    res = anchor_root(
        w3=w3,
        address=addr,
        priv_key=key,
        root=local_root,
        schema=schema,
        bundle_uri=bundle_uri,
    )

    explorer = CHAINS.get(name, {}).get("explorer")
    tx_hash = res["tx_hash"] if res["tx_hash"].startswith("0x") else "0x" + res["tx_hash"]

    receipt: Dict[str, Any] = {
        "chain": name,
        "chain_id": res["chain_id"],
        "contract": res["contract"],
        "anchor_id": res["anchor_id"],
        "root": local_root,
        "schema": schema,
        "bundle_uri": bundle_uri,
        "submitter": res["submitter"],
        "tx_hash": tx_hash,
        "block_number": res["block_number"],
        "gas_used": res["gas_used"],
        "status": res["status"],
        "explorer_url": f"{explorer}/tx/{tx_hash}" if explorer else None,
    }

    receipt_path = run_path / RECEIPT_FILENAME
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    manifest.log(
        "STAGE 3",
        "anchored",
        chain=name,
        anchor_id=res["anchor_id"],
        block=res["block_number"],
        tx=tx_hash[:14] + "...",
        gas=res["gas_used"],
    )
    manifest.artifact("STAGE 3", receipt_path)

    console.print(f"[bold green]anchored on {name}[/bold green]  id={res['anchor_id']}")
    console.print(f"  tx    {tx_hash}")
    console.print(f"  block {res['block_number']}  gas {res['gas_used']}")
    console.print(f"  root  {local_root}")
    if receipt["explorer_url"]:
        console.print(f"  {receipt['explorer_url']}")

    return receipt
