// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "../src/EvidenceRegistry.sol";

/// Minimal cheatcode surface — avoids vendoring forge-std for an offline build.
interface Vm {
    struct Log {
        bytes32[] topics;
        bytes data;
        address emitter;
    }

    function warp(uint256) external;
    function prank(address) external;
    function recordLogs() external;
    function getRecordedLogs() external returns (Log[] memory);
}

contract EvidenceRegistryTest {
    Vm private constant vm =
        Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    EvidenceRegistry registry;

    bytes32 constant ROOT_1 = keccak256("root-1");
    bytes32 constant ROOT_2 = keccak256("root-2");
    bytes32 constant SCHEMA = keccak256("faceproof.evidence.v1");
    string constant URI_1 = "ipfs://QmBundle1";

    event Anchored(
        uint256 indexed id,
        bytes32 indexed root,
        bytes32 indexed schema,
        string bundleURI,
        address submitter,
        uint256 anchoredAt
    );

    function setUp() public {
        registry = new EvidenceRegistry();
    }

    // ── basics ──────────────────────────────────────────────────────────

    function testInitialTotalIsZero() public view {
        require(registry.total() == 0, "total != 0");
    }

    function testAnchorSuccessAndTotalProgression() public {
        require(registry.total() == 0, "pre total");
        uint256 id0 = registry.anchor(ROOT_1, SCHEMA, URI_1);
        require(id0 == 0, "id0");
        require(registry.total() == 1, "total 1");
        uint256 id1 = registry.anchor(ROOT_2, SCHEMA, "ipfs://2");
        require(id1 == 1, "id1");
        require(registry.total() == 2, "total 2");
    }

    // ── lookups ─────────────────────────────────────────────────────────

    function testLookupById() public {
        vm.warp(1_800_000_000);
        registry.anchor(ROOT_1, SCHEMA, URI_1);

        EvidenceRegistry.Record memory r = registry.get(0);
        require(r.root == ROOT_1, "root");
        require(r.schema == SCHEMA, "schema");
        require(r.submitter == address(this), "submitter");
        require(r.anchoredAt == 1_800_000_000, "anchoredAt");
        require(
            keccak256(bytes(r.bundleURI)) == keccak256(bytes(URI_1)),
            "uri"
        );
    }

    function testLookupByRoot() public {
        registry.anchor(ROOT_1, SCHEMA, URI_1);
        registry.anchor(ROOT_2, SCHEMA, "ipfs://2");
        require(registry.idOf(ROOT_1) == 0, "idOf 1");
        require(registry.idOf(ROOT_2) == 1, "idOf 2");
        require(registry.isAnchored(ROOT_1), "isAnchored");
        require(!registry.isAnchored(keccak256("nope")), "!isAnchored");
    }

    // ── reverts ─────────────────────────────────────────────────────────

    function testZeroRootReverts() public {
        try registry.anchor(bytes32(0), SCHEMA, URI_1) {
            revert("expected ZeroRoot");
        } catch (bytes memory err) {
            require(bytes4(err) == EvidenceRegistry.ZeroRoot.selector, "sel");
        }
    }

    function testDuplicateRootReverts() public {
        registry.anchor(ROOT_1, SCHEMA, URI_1);
        try registry.anchor(ROOT_1, SCHEMA, "ipfs://other") {
            revert("expected RootAlreadyAnchored");
        } catch (bytes memory err) {
            require(
                bytes4(err) == EvidenceRegistry.RootAlreadyAnchored.selector,
                "sel"
            );
        }
    }

    function testUnknownAnchorReverts() public {
        try registry.get(0) {
            revert("expected UnknownAnchor (get)");
        } catch (bytes memory err) {
            require(bytes4(err) == EvidenceRegistry.UnknownAnchor.selector, "get");
        }
        try registry.idOf(keccak256("missing")) {
            revert("expected UnknownAnchor (idOf)");
        } catch (bytes memory err) {
            require(bytes4(err) == EvidenceRegistry.UnknownAnchor.selector, "idOf");
        }
        bytes32[] memory empty = new bytes32[](0);
        try registry.verifyField(7, bytes32(uint256(1)), empty) {
            revert("expected UnknownAnchor (verifyField)");
        } catch (bytes memory err) {
            require(
                bytes4(err) == EvidenceRegistry.UnknownAnchor.selector,
                "verifyField"
            );
        }
    }

    // ── event ───────────────────────────────────────────────────────────

    function testAnchoredEventIsEmitted() public {
        vm.warp(1_812_345_678);
        vm.recordLogs();
        registry.anchor(ROOT_1, SCHEMA, URI_1);
        Vm.Log[] memory logs = vm.getRecordedLogs();

        require(logs.length == 1, "one log");
        Vm.Log memory e = logs[0];
        require(e.emitter == address(registry), "emitter");
        require(e.topics[0] == keccak256(
            "Anchored(uint256,bytes32,bytes32,string,address,uint256)"
        ), "sig");
        require(uint256(e.topics[1]) == 0, "id topic");
        require(e.topics[2] == ROOT_1, "root topic");
        require(e.topics[3] == SCHEMA, "schema topic");

        (string memory uri, address submitter, uint256 at) =
            abi.decode(e.data, (string, address, uint256));
        require(keccak256(bytes(uri)) == keccak256(bytes(URI_1)), "uri data");
        require(submitter == address(this), "submitter data");
        require(at == 1_812_345_678, "at data");
    }

    // ── selective disclosure over a full 8-leaf tree ────────────────────

    function _hashPair(bytes32 a, bytes32 b) internal pure returns (bytes32) {
        return a <= b
            ? keccak256(abi.encodePacked(a, b))
            : keccak256(abi.encodePacked(b, a));
    }

    function testVerifyFieldOnEightLeafTree() public {
        // leaf_i = keccak(keccak(payload_i)) — same rule as faceproof/merkle.py
        bytes32[8] memory leaves;
        for (uint256 i = 0; i < 8; ++i) {
            leaves[i] = keccak256(
                abi.encodePacked(keccak256(abi.encodePacked("group", i)))
            );
        }

        bytes32[4] memory l1;
        for (uint256 i = 0; i < 4; ++i) {
            l1[i] = _hashPair(leaves[2 * i], leaves[2 * i + 1]);
        }
        bytes32[2] memory l2;
        l2[0] = _hashPair(l1[0], l1[1]);
        l2[1] = _hashPair(l1[2], l1[3]);
        bytes32 root = _hashPair(l2[0], l2[1]);

        uint256 id = registry.anchor(root, SCHEMA, URI_1);

        // proof for leaf index 2 (match_location): [leaves[3], l1[0], l2[1]]
        bytes32[] memory proof = new bytes32[](3);
        proof[0] = leaves[3];
        proof[1] = l1[0];
        proof[2] = l2[1];

        require(registry.verifyField(id, leaves[2], proof), "valid proof");

        bytes32 tampered = keccak256("tampered-match_location");
        require(!registry.verifyField(id, tampered, proof), "tampered leaf");

        bytes32[] memory badProof = new bytes32[](3);
        badProof[0] = leaves[3];
        badProof[1] = keccak256("wrong");
        badProof[2] = l2[1];
        require(!registry.verifyField(id, leaves[2], badProof), "tampered proof");
    }
}
