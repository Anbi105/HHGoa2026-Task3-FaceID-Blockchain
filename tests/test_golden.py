"""Golden vectors — the encoding contract with Stage 3.

§14 lists "different roots on two machines" as a failure mode and
prescribes the fix: *add a test asserting a fixed input hashes to a fixed
value*.  These are that test for Stage 1's half of the contract.

If one of these fails, the byte encoding changed.  Do not update the
expected value to make it pass — a changed encoding invalidates every
commitment already anchored on chain.  Find out what moved.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from faceproof.consent import _keccak, embedding_bytes, embedding_commitment

# A deterministic unit vector built from fixed arithmetic, so it does not
# depend on any RNG implementation.
GOLDEN_EMBEDDING = (
    lambda v: (v / np.linalg.norm(v)).astype("float32")
)(np.array([(i % 17) - 8 for i in range(512)], dtype="float32"))

GOLDEN_SALT = bytes(range(32))

EXPECTED_EMBEDDING_SHA256 = (
    "0f167ffac9140632d1e27d33d738e80fa20a8ee9f69489fb9577006a7c1e5d66"
)
EXPECTED_COMMITMENT = (
    "9c562617085ea9400e4bff3df32941b3440d7b4122cc63f786282cb884f76b73"
)


class TestGoldenEncoding:
    def test_embedding_bytes_are_pinned(self):
        """The 2048-byte little-endian float32 encoding must not drift."""
        digest = hashlib.sha256(embedding_bytes(GOLDEN_EMBEDDING)).hexdigest()
        assert digest == EXPECTED_EMBEDDING_SHA256

    def test_commitment_is_pinned(self):
        """keccak256(salt ‖ embedding) — the Merkle leaf Stage 3 anchors."""
        commitment, _ = embedding_commitment(GOLDEN_EMBEDDING, salt=GOLDEN_SALT)
        assert commitment.hex() == EXPECTED_COMMITMENT

    def test_keccak_is_ethereum_keccak_not_sha3(self):
        """§14: 'Merkle proof valid in Python, invalid in Solidity' is
        SHA-256 or NIST SHA3 where keccak256 was required.  This is the
        published keccak256 of the empty string."""
        assert _keccak(b"").hex() == (
            "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
        )

    def test_keccak_differs_from_sha3(self):
        assert _keccak(b"faceproof") != hashlib.sha3_256(b"faceproof").digest()

    def test_byte_order_is_little_regardless_of_host_array(self):
        big_endian = GOLDEN_EMBEDDING.astype(">f4")
        assert (
            hashlib.sha256(embedding_bytes(big_endian)).hexdigest()
            == EXPECTED_EMBEDDING_SHA256
        )

    def test_encoding_is_2048_bytes(self):
        assert len(embedding_bytes(GOLDEN_EMBEDDING)) == 512 * 4
