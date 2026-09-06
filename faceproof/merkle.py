"""Binary Merkle tree over the eight evidence groups (Stage 3, S7).

Design, fixed so the Python here and ``MerkleLite`` in
``contracts/src/EvidenceRegistry.sol`` agree byte-for-byte:

* **Leaf** = ``keccak256(keccak256(payload))``.  The double hash is a
  cheap domain separation between leaves and internal nodes - an attacker
  cannot present an internal node as if it were a leaf.
* **Internal node** = ``keccak256(min(a, b) || max(a, b))``.  Sorting the
  pair means a proof carries only sibling hashes, no left/right bits, and
  the Solidity verifier is a two-line loop.
* **Shape**: exactly a power of two leaves.  The bundle always has eight
  groups, so the tree is a full tree of depth three and no duplicate-last
  padding is ever needed.

``build`` returns *layers* (``layers[0]`` = leaves, ``layers[-1]`` =
``[root]``); ``root`` / ``proof`` take that structure so a tree is walked
once, not rebuilt per query.
"""

from __future__ import annotations

from typing import Callable, List

try:  # the web3 stack ships this; it is the reference implementation
    from eth_utils import keccak  # type: ignore
except ImportError:  # pragma: no cover - env-dependent fallback
    # pycryptodome is already a Stage 1 dependency, so keccak is always available
    from Crypto.Hash import keccak as _pycryptodome_keccak

    def keccak(data: bytes) -> bytes:  # type: ignore[misc]
        h = _pycryptodome_keccak.new(digest_bits=256)
        h.update(bytes(data))
        return h.digest()

_keccak: Callable[[bytes], bytes] = keccak

BYTES32 = 32


# ---------------------------------------------------------------------------
# Hash primitives
# ---------------------------------------------------------------------------


def leaf(payload: bytes) -> bytes:
    """Leaf hash of an already-canonicalised group: ``keccak(keccak(payload))``."""
    return keccak(keccak(payload))


def _pair(a: bytes, b: bytes) -> bytes:
    """Parent of two nodes, sorted so order does not matter (S7)."""
    return keccak(a + b) if a <= b else keccak(b + a)


# ---------------------------------------------------------------------------
# Tree
# ---------------------------------------------------------------------------


def build(leaves: List[bytes]) -> List[List[bytes]]:
    """Build every layer of the tree from a power-of-two list of leaf hashes.

    Returns ``[leaves, ..., [root]]``.  Raises ``ValueError`` on an empty
    list, a non-power-of-two length, or a leaf that is not 32 bytes.
    """
    n = len(leaves)
    if n == 0 or (n & (n - 1)) != 0:
        raise ValueError(f"leaf count must be a non-zero power of two, got {n}")
    for i, lf in enumerate(leaves):
        if not isinstance(lf, (bytes, bytearray)) or len(lf) != BYTES32:
            raise ValueError(f"leaf {i} must be {BYTES32} bytes")

    layers: List[List[bytes]] = [list(leaves)]
    while len(layers[-1]) > 1:
        cur = layers[-1]
        layers.append([_pair(cur[i], cur[i + 1]) for i in range(0, len(cur), 2)])
    return layers


def root(layers: List[List[bytes]]) -> bytes:
    """Root hash from the structure returned by :func:`build`."""
    return layers[-1][0]


def proof(layers: List[List[bytes]], index: int) -> List[bytes]:
    """Audit path (sibling hashes, leaf level -> up) for the leaf at ``index``."""
    if not (0 <= index < len(layers[0])):
        raise IndexError(f"leaf index {index} out of range [0, {len(layers[0])})")
    out: List[bytes] = []
    i = index
    for level in layers[:-1]:
        out.append(level[i ^ 1])
        i //= 2
    return out


def verify(leaf_hash: bytes, proof_: List[bytes], root_: bytes) -> bool:
    """Recompute the root from a leaf + audit path and compare to ``root_``.

    Uses the same sorted-pair rule as :func:`_pair`, so this returns exactly
    what the contract's ``verifyField`` returns for the same inputs.
    """
    computed = leaf_hash
    for sib in proof_:
        computed = _pair(computed, sib)
    return computed == root_


# ---------------------------------------------------------------------------
# Convenience for the 8-group bundle
# ---------------------------------------------------------------------------


def leaves_from_payloads(payloads: List[bytes]) -> List[bytes]:
    """``[leaf(p) for p in payloads]`` - the canonical group bytes -> leaf hashes."""
    return [leaf(p) for p in payloads]


def hexstr(b: bytes) -> str:
    """32 raw bytes -> ``0x``-prefixed 64-char hex."""
    return "0x" + bytes(b).hex()


def unhex(s: str | bytes) -> bytes:
    """Inverse of :func:`hexstr`; also accepts raw 32-byte input unchanged."""
    if isinstance(s, (bytes, bytearray)):
        b = bytes(s)
    else:
        b = bytes.fromhex(s[2:] if s.startswith("0x") else s)
    if len(b) != BYTES32:
        raise ValueError(f"expected {BYTES32} bytes, got {len(b)}")
    return b
