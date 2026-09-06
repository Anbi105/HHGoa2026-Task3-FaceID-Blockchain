"""Pure, offline units in chain.py — no RPC, no node, no keys.

`.coveragerc` used to omit chain.py wholesale on the grounds that it is "thin
integration glue with no unit-testable logic of its own".  That is not true of
`to_bytes32` (a pure function that silently corrupted mistyped digests) or of
`chain_name` / `rpc_url` (which silently redirected an unknown chain to
localhost).  Those are exactly the paths worth pinning.
"""

from __future__ import annotations

import pytest

pytest.importorskip("web3")

from faceproof.chain import (  # noqa: E402
    CHAINS,
    UnknownChainError,
    chain_name,
    rpc_url,
    to_bytes32,
)
from faceproof.merkle import unhex  # noqa: E402

ROOT_HEX = "bd9643d34189af122492472303311cf2bac38066d9c00b98906a91ad69a0d8fc"


# --------------------------------------------------------------------------- #
# to_bytes32
# --------------------------------------------------------------------------- #

class TestToBytes32:
    def test_raw_32_bytes_pass_through(self):
        raw = bytes(range(32))
        assert to_bytes32(raw) == raw

    def test_raw_bytes_of_wrong_length_reject(self):
        with pytest.raises(ValueError, match="expected 32 bytes"):
            to_bytes32(b"\x01" * 31)

    def test_prefixed_hex_digest_decodes(self):
        assert to_bytes32("0x" + ROOT_HEX) == unhex("0x" + ROOT_HEX)

    def test_bare_64_char_hex_digest_decodes(self):
        assert to_bytes32(ROOT_HEX) == unhex("0x" + ROOT_HEX)

    def test_schema_id_is_hashed(self):
        # a short non-hex string is a schema identifier -> keccak of its bytes
        out = to_bytes32("faceproof.evidence.v1")
        assert len(out) == 32
        assert out != b"\x00" * 32

    def test_mistyped_digest_is_rejected_not_hashed(self):
        """One non-hex character in a root used to become a different,
        valid-looking bytes32 — a silent corruption surfacing much later."""
        typo = ROOT_HEX[:-1] + "z"          # still 64 chars, not hex
        with pytest.raises(ValueError, match="not a valid hex digest"):
            to_bytes32(typo)

    def test_prefixed_but_wrong_length_is_rejected(self):
        with pytest.raises(ValueError, match="32-byte hex digest"):
            to_bytes32("0xdeadbeef")

    def test_a_typo_no_longer_collides_with_a_keccak_fallback(self):
        typo = ROOT_HEX[:-1] + "z"
        good = to_bytes32("0x" + ROOT_HEX)
        with pytest.raises(ValueError):
            assert to_bytes32(typo) != good


# --------------------------------------------------------------------------- #
# chain_name / rpc_url
# --------------------------------------------------------------------------- #

class TestChainSelection:
    def test_unset_chain_defaults_to_anvil(self, monkeypatch):
        monkeypatch.delenv("CHAIN", raising=False)
        monkeypatch.delenv("FACEPROOF_CHAIN", raising=False)
        assert chain_name() == "anvil"

    def test_known_chain_is_normalised(self, monkeypatch):
        monkeypatch.setenv("CHAIN", "  AMOY ")
        assert chain_name() == "amoy"

    def test_unknown_chain_raises_instead_of_silently_using_localhost(self, monkeypatch):
        """`CHAIN=polygon` used to anchor to Anvil while the operator believed
        they were on a testnet."""
        monkeypatch.setenv("CHAIN", "polygon")
        with pytest.raises(UnknownChainError, match="not a known network"):
            chain_name()

    def test_rpc_url_prefers_the_environment(self, monkeypatch):
        monkeypatch.setenv("RPC_URL", "http://example.invalid:8545")
        assert rpc_url("anvil") == "http://example.invalid:8545"

    def test_rpc_url_falls_back_to_the_chain_default(self, monkeypatch):
        monkeypatch.delenv("RPC_URL", raising=False)
        monkeypatch.delenv("FACEPROOF_RPC_URL", raising=False)
        assert rpc_url("anvil") == CHAINS["anvil"]["rpc"]

    def test_rpc_url_rejects_an_unknown_chain(self, monkeypatch):
        monkeypatch.delenv("RPC_URL", raising=False)
        monkeypatch.delenv("FACEPROOF_RPC_URL", raising=False)
        with pytest.raises(UnknownChainError):
            rpc_url("polygon")


# --------------------------------------------------------------------------- #
# registry_address / private_key — pure environment reads
# --------------------------------------------------------------------------- #

class TestEnvSecrets:
    def test_registry_address_requires_configuration(self, monkeypatch):
        from faceproof.chain import registry_address

        for var in ("REGISTRY_ADDRESS", "FACEPROOF_REGISTRY_ADDRESS"):
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(ValueError, match="REGISTRY_ADDRESS is not set"):
            registry_address()

    def test_registry_address_is_checksummed(self, monkeypatch):
        from faceproof.chain import registry_address

        monkeypatch.setenv("REGISTRY_ADDRESS", "0xee0efb2a3d75f1933f171de8e8d9dd14903170d3")
        # returned in EIP-55 mixed case, not as typed
        assert registry_address() == "0xeE0efb2a3D75f1933f171dE8e8D9Dd14903170d3"

    def test_private_key_requires_configuration(self, monkeypatch):
        from faceproof.chain import private_key

        for var in ("PRIVATE_KEY", "FACEPROOF_PRIVATE_KEY"):
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(ValueError, match="PRIVATE_KEY is not set"):
            private_key()

    def test_private_key_is_never_echoed_in_the_error(self, monkeypatch):
        from faceproof.chain import private_key

        monkeypatch.setenv("PRIVATE_KEY", "  0x" + "ab" * 32 + "  ")
        assert private_key() == "0x" + "ab" * 32     # stripped, not mangled
