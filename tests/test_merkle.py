"""Stage 3 — keccak Merkle tree, sorted pairs, power-of-two shape (§7)."""

import pytest

from faceproof.canonical import canon
from faceproof.merkle import (
    _pair,
    build,
    hexstr,
    keccak,
    leaf,
    leaves_from_payloads,
    proof,
    root,
    unhex,
    verify,
)


def _payloads(n=8):
    return [canon({"i": i, "v": f"val-{i}"}) for i in range(n)]


def test_leaf_is_double_keccak():
    p = canon({"x": "1"})
    assert leaf(p) == keccak(keccak(p))
    assert len(leaf(p)) == 32


def test_pair_is_sorted():
    a, b = b"\x01" * 32, b"\x02" * 32
    assert _pair(a, b) == _pair(b, a)
    assert _pair(a, b) == keccak(a + b)


def test_build_rejects_bad_shape():
    with pytest.raises(ValueError, match="power of two"):
        build([])
    for n in (3, 5, 6, 7):
        with pytest.raises(ValueError, match="power of two"):
            build(leaves_from_payloads(_payloads(n)))


def test_layers_shape_for_eight():
    layers = build(leaves_from_payloads(_payloads(8)))
    assert [len(x) for x in layers] == [8, 4, 2, 1]
    assert root(layers) == layers[-1][0]


def test_proof_roundtrip_all_indices():
    leaves = leaves_from_payloads(_payloads(8))
    layers = build(leaves)
    r = root(layers)
    for i in range(8):
        pth = proof(layers, i)
        assert len(pth) == 3
        assert verify(leaves[i], pth, r)


def test_wrong_leaf_or_proof_fails():
    leaves = leaves_from_payloads(_payloads(8))
    layers = build(leaves)
    r = root(layers)
    assert not verify(leaf(canon({"i": 99})), proof(layers, 0), r)
    bad = list(proof(layers, 0))
    bad[0] = bytes(x ^ 0xFF for x in bad[0])
    assert not verify(leaves[0], bad, r)


def test_deterministic_root():
    r1 = root(build(leaves_from_payloads(_payloads(8))))
    r2 = root(build(leaves_from_payloads(_payloads(8))))
    assert r1 == r2


def test_build_rejects_wrong_sized_leaf():
    with pytest.raises(ValueError, match="must be 32 bytes"):
        build([b"\x00" * 32, b"short"])


def test_proof_index_out_of_range():
    layers = build(leaves_from_payloads(_payloads(4)))
    with pytest.raises(IndexError):
        proof(layers, 4)


def test_keccak_matches_double_hash_helper():
    assert leaf(b"abc") == keccak(keccak(b"abc"))


def test_hex_helpers():
    b = b"\xab" * 32
    assert hexstr(b) == "0x" + "ab" * 32
    assert unhex(hexstr(b)) == b
    with pytest.raises(ValueError):
        unhex("0xdead")
