"""Stage 3 — Web3.py against a local Anvil node (§18-20).

Skipped automatically unless an Anvil node is reachable on 127.0.0.1:8545
and the Foundry artifact has been built (`forge build` in contracts/).
"""

import json

import pytest

from faceproof.bundle import assemble_bundle
from faceproof.canonical import q
from faceproof.merkle import unhex
from faceproof.stage2_adapter import normalize

web3 = pytest.importorskip("web3")
from web3 import Web3  # noqa: E402

from faceproof.chain import (  # noqa: E402
    ARTIFACT_PATH,
    anchor_root,
    get_abi,
    get_bytecode,
    get_record,
    id_of,
    total,
    verify_field,
)

ANVIL_RPC = "http://127.0.0.1:8545"
# Anvil's well-known unfunded-in-public dev account #0 — safe to hard-code.
ANVIL_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


@pytest.fixture(scope="module")
def w3():
    if not ARTIFACT_PATH.exists():
        pytest.skip("run `forge build` in contracts/ first")
    w = Web3(Web3.HTTPProvider(ANVIL_RPC, request_kwargs={"timeout": 5}))
    if not w.is_connected():
        pytest.skip("no Anvil node on 127.0.0.1:8545")
    return w


@pytest.fixture(scope="module")
def registry(w3):
    acct = w3.eth.account.from_key(ANVIL_KEY)
    contract = w3.eth.contract(abi=get_abi(), bytecode=get_bytecode())
    tx = contract.constructor().build_transaction(
        {
            "from": acct.address,
            "nonce": w3.eth.get_transaction_count(acct.address),
            "gasPrice": w3.eth.gas_price,
            "chainId": w3.eth.chain_id,
        }
    )
    tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.25)
    signed = acct.sign_transaction(tx)
    rcpt = w3.eth.wait_for_transaction_receipt(
        w3.eth.send_raw_transaction(signed.raw_transaction)
    )
    return rcpt["contractAddress"]


def _bundle(tmp_path):
    stage1 = {
        "status": "accepted",
        "model_id": "insightface/buffalo_l@w600k_r50",
        "quality": {"det_score": q(0.95), "blur_var": q(62.0)},
        "consent": {
            "subject_commitment": "0x" + "a1" * 32,
            "granted_at": "2026-09-06T10:00:00Z",
            "scope": "face_probe_demo",
        },
        "embedding": {"commitment": "0x" + "b2" * 32},
    }
    stage2 = normalize(
        {
            "fusion_outcome": "CORROBORATED",
            "snapshot_id": "snap-anvil",
            "margin": 0.2,
            "match": {
                "platform": "bluesky",
                "post_url": "https://bsky.app/profile/a.bsky.social/post/3kanvil",
                "post_uri": "at://did:plc:a/app.bsky.feed.post/3kanvil",
                "author_did": "did:plc:a",
                "author_handle": "a.bsky.social",
                "text": "live demo",
                "image_sha256": "c3" * 32,
                "phash": "12345678",
                "score": 0.88,
            },
        },
        source="test",
    )
    return assemble_bundle(tmp_path, stage1, stage2)


def test_connected(w3):
    assert w3.eth.chain_id == 31337


def test_abi_from_foundry_artifact_has_full_interface():
    names = {i["name"] for i in get_abi() if i.get("type") == "function"}
    assert {"anchor", "total", "get", "idOf", "verifyField"} <= names


def test_anchor_lookup_and_selective_disclosure(w3, registry, tmp_path):
    bundle, proofs = _bundle(tmp_path)
    root = bundle["merkle_root"]

    before = total(w3, registry)
    res = anchor_root(w3, registry, ANVIL_KEY, root, bundle["schema_id"], "ipfs://demo")
    assert res["status"] == 1
    assert res["anchor_id"] == before

    assert id_of(w3, registry, root) == res["anchor_id"]
    assert total(w3, registry) == before + 1

    rec = get_record(w3, registry, res["anchor_id"])
    assert rec["root"].lower() == root.lower()
    assert rec["bundle_uri"] == "ipfs://demo"

    entry = proofs["groups"]["match_location"]
    assert verify_field(w3, registry, res["anchor_id"], entry["leaf"], entry["proof"]) is True

    # tampered leaf must fail on-chain
    bad = "0x" + "de" * 32
    assert verify_field(w3, registry, res["anchor_id"], bad, entry["proof"]) is False


def test_duplicate_root_reverts(w3, registry):
    root = "0x" + "7c" * 32  # arbitrary, unique to this test
    schema = "faceproof.evidence.v1"
    anchor_root(w3, registry, ANVIL_KEY, root, schema, "")
    with pytest.raises(Exception):
        anchor_root(w3, registry, ANVIL_KEY, root, schema, "")


def test_zero_root_reverts(w3, registry):
    with pytest.raises(Exception):
        anchor_root(w3, registry, ANVIL_KEY, "0x" + "00" * 32, "s", "")
