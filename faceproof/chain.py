"""Web3.py interaction with the deployed ``EvidenceRegistry`` (Stage 3, S18, S19).

Two networks, same code path:

* **Polygon Amoy** (chain id ``80002``) - the live target.  A proof-of-stake
  side-chain, so the POA extra-data middleware is injected.
* **Anvil** (chain id ``31337``) - the local fallback used by tests and the
  offline demo.

The ABI is loaded **only** from the Foundry build artifact
``contracts/out/EvidenceRegistry.sol/EvidenceRegistry.json`` - never a
hand-maintained copy, which is how the Python and Solidity sides drift
apart.  Run ``forge build`` first.

Secrets come from the environment (``PRIVATE_KEY``, ``REGISTRY_ADDRESS``);
nothing sensitive is hard-coded or logged.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from eth_account import Account
from eth_utils import keccak
from web3 import Web3

try:  # web3 >= 7 name
    from web3.middleware import ExtraDataToPOAMiddleware as _POA_MIDDLEWARE
except ImportError:  # pragma: no cover - older web3
    try:
        from web3.middleware import geth_poa_middleware as _POA_MIDDLEWARE
    except ImportError:
        _POA_MIDDLEWARE = None

from faceproof.config import _REPO_ROOT

HTTP_TIMEOUT_SECONDS = 30
RECEIPT_TIMEOUT_SECONDS = 180

ARTIFACT_PATH = (
    _REPO_ROOT / "contracts" / "out" / "EvidenceRegistry.sol" / "EvidenceRegistry.json"
)

# name -> (chain_id, default rpc, needs POA middleware, explorer base)
CHAINS: Dict[str, Dict[str, Any]] = {
    "anvil": {
        "chain_id": 31337,
        "rpc": "http://127.0.0.1:8545",
        "poa": False,
        "explorer": None,
    },
    "amoy": {
        "chain_id": 80002,
        # publicnode's Bor RPC - the endpoint the live anchor was sent through;
        # rpc-amoy.polygon.technology had intermittent DNS failures.  Override
        # with RPC_URL for any other provider.
        "rpc": "https://polygon-amoy-bor-rpc.publicnode.com",
        "poa": True,
        "explorer": "https://amoy.polygonscan.com",
    },
}


# ---------------------------------------------------------------------------
# Configuration (environment first, then per-chain defaults)
# ---------------------------------------------------------------------------


def chain_name() -> str:
    name = os.environ.get("CHAIN") or os.environ.get("FACEPROOF_CHAIN") or "anvil"
    name = name.strip().lower()
    return name if name in CHAINS else "anvil"


def rpc_url(name: Optional[str] = None) -> str:
    env = os.environ.get("RPC_URL") or os.environ.get("FACEPROOF_RPC_URL")
    if env:
        return env.strip()
    return CHAINS[name or chain_name()]["rpc"]


def registry_address() -> str:
    addr = (
        os.environ.get("REGISTRY_ADDRESS")
        or os.environ.get("FACEPROOF_REGISTRY_ADDRESS")
        or ""
    ).strip()
    if not addr:
        raise ValueError(
            "REGISTRY_ADDRESS is not set - deploy EvidenceRegistry "
            "(`make deploy`) and export its address, or set it in .env"
        )
    return Web3.to_checksum_address(addr)


def private_key() -> str:
    pk = (
        os.environ.get("PRIVATE_KEY")
        or os.environ.get("FACEPROOF_PRIVATE_KEY")
        or ""
    ).strip()
    if not pk:
        raise ValueError(
            "PRIVATE_KEY is not set - export the key of a funded account "
            "for the target chain (never commit it)"
        )
    return pk


# ---------------------------------------------------------------------------
# Artifact / ABI
# ---------------------------------------------------------------------------


def load_artifact() -> Dict[str, Any]:
    if not ARTIFACT_PATH.exists():
        raise FileNotFoundError(
            f"Foundry artifact not found at {ARTIFACT_PATH}. Run `forge build` "
            f"in contracts/ first."
        )
    return json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))


def get_abi() -> List[Dict[str, Any]]:
    return load_artifact()["abi"]


def get_bytecode() -> str:
    obj = load_artifact().get("bytecode", {})
    return obj.get("object", obj) if isinstance(obj, dict) else obj


# ---------------------------------------------------------------------------
# Web3 wiring
# ---------------------------------------------------------------------------


def get_w3(url: Optional[str] = None, *, name: Optional[str] = None) -> Web3:
    """Connected :class:`Web3` with a 30 s HTTP timeout and POA middleware on Amoy."""
    name = name or chain_name()
    url = url or rpc_url(name)
    w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": HTTP_TIMEOUT_SECONDS}))
    if CHAINS.get(name, {}).get("poa") and _POA_MIDDLEWARE is not None:
        try:
            w3.middleware_onion.inject(_POA_MIDDLEWARE, layer=0)
        except ValueError:
            pass  # already present
    return w3


def get_contract(w3: Web3, address: Optional[str] = None):
    return w3.eth.contract(
        address=Web3.to_checksum_address(address or registry_address()),
        abi=get_abi(),
    )


def to_bytes32(value: Union[str, bytes]) -> bytes:
    """Normalise to 32 bytes.

    * 32 raw bytes -> unchanged
    * ``0x`` + 64 hex -> decoded
    * any other string (e.g. a schema id like ``faceproof.evidence.v1``)
      -> ``keccak256(utf-8 bytes)``
    """
    if isinstance(value, (bytes, bytearray)):
        b = bytes(value)
        if len(b) != 32:
            raise ValueError(f"expected 32 bytes, got {len(b)}")
        return b
    s = value.strip()
    hexpart = s[2:] if s.startswith("0x") else s
    if len(hexpart) == 64:
        try:
            return bytes.fromhex(hexpart)
        except ValueError:
            pass
    return keccak(text=s)


# ---------------------------------------------------------------------------
# Transactions / calls
# ---------------------------------------------------------------------------


def anchor_root(
    w3: Web3,
    address: str,
    priv_key: str,
    root: Union[str, bytes],
    schema: Union[str, bytes],
    bundle_uri: str,
) -> Dict[str, Any]:
    """Send ``anchor(root, schema, bundleURI)`` and return a normalised receipt.

    The returned dict includes the parsed ``anchor_id`` from the ``Anchored``
    event so callers never have to guess it.
    """
    contract = get_contract(w3, address)
    acct = Account.from_key(priv_key)

    root_b = to_bytes32(root)
    schema_b = to_bytes32(schema)
    fn = contract.functions.anchor(root_b, schema_b, bundle_uri)

    tx = fn.build_transaction(
        {
            "chainId": w3.eth.chain_id,
            "from": acct.address,
            "nonce": w3.eth.get_transaction_count(acct.address, "pending"),
            "gasPrice": w3.eth.gas_price,
        }
    )
    tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.25)

    signed = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(
        tx_hash, timeout=RECEIPT_TIMEOUT_SECONDS
    )

    anchor_id: Optional[int] = None
    try:
        events = contract.events.Anchored().process_receipt(receipt)
        if events:
            anchor_id = int(events[0]["args"]["id"])
    except Exception:  # pragma: no cover - fall back to a view call
        pass
    if anchor_id is None:
        anchor_id = int(contract.functions.idOf(root_b).call())

    return {
        "tx_hash": receipt["transactionHash"].hex()
        if hasattr(receipt["transactionHash"], "hex")
        else str(receipt["transactionHash"]),
        "block_number": int(receipt["blockNumber"]),
        "gas_used": int(receipt["gasUsed"]),
        "status": int(receipt.get("status", 1)),
        "anchor_id": anchor_id,
        "submitter": acct.address,
        "contract": Web3.to_checksum_address(address),
        "chain_id": int(w3.eth.chain_id),
    }


def get_record(w3: Web3, address: str, anchor_id: int) -> Dict[str, Any]:
    rec = get_contract(w3, address).functions.get(anchor_id).call()
    return {
        "root": "0x" + rec[0].hex(),
        "anchored_at": int(rec[1]),
        "submitter": rec[2],
        "schema": "0x" + rec[3].hex(),
        "bundle_uri": rec[4],
    }


def id_of(w3: Web3, address: str, root: Union[str, bytes]) -> int:
    return int(get_contract(w3, address).functions.idOf(to_bytes32(root)).call())


def total(w3: Web3, address: str) -> int:
    return int(get_contract(w3, address).functions.total().call())


def verify_field(
    w3: Web3,
    address: str,
    anchor_id: int,
    leaf: Union[str, bytes],
    proof: List[Union[str, bytes]],
) -> bool:
    """Call the contract's ``verifyField`` - on-chain selective-disclosure check."""
    contract = get_contract(w3, address)
    return bool(
        contract.functions.verifyField(
            anchor_id, to_bytes32(leaf), [to_bytes32(p) for p in proof]
        ).call()
    )
