// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;
import "../src/EvidenceRegistry.sol";

contract EvidenceRegistryTest {
    EvidenceRegistry registry;
    bytes32 root = keccak256("root");
    function setUp() public { registry = new EvidenceRegistry(); }
    function testAnchorLookupAndMetadata() public {
        registry.anchor(root,"faceproof.evidence.v1","ipfs://bundle");
        require(registry.idOf(root)==0,"lookup"); EvidenceRegistry.Anchor memory a=registry.get(0);
        require(a.root==root && a.submitter==address(this),"stored root/submitter");
        require(keccak256(bytes(a.schema))==keccak256("faceproof.evidence.v1"),"schema"); require(keccak256(bytes(a.uri))==keccak256("ipfs://bundle"),"uri");
    }
    function testDuplicateAndZeroRejected() public {
        registry.anchor(root,"s","u"); try registry.anchor(root,"s","u") { revert("duplicate accepted"); } catch {}
        try registry.anchor(bytes32(0),"s","u") { revert("zero accepted"); } catch {}
    }
    function testMultipleAnchors() public { registry.anchor(root,"s","u"); registry.anchor(keccak256("two"),"s","u"); require(registry.idOf(keccak256("two"))==1,"second"); }
    function testMerkleProofAndTamperedLeaf() public {
        bytes32 leaf=keccak256("leaf"); bytes32 sibling=keccak256("sibling"); bytes32 parent=keccak256(abi.encodePacked(leaf < sibling ? leaf:sibling,leaf < sibling ? sibling:leaf)); registry.anchor(parent,"s","u");
        bytes32[] memory proof=new bytes32[](1); proof[0]=sibling; require(registry.verifyField(0,leaf,proof),"proof"); require(!registry.verifyField(0,keccak256("tampered"),proof),"tamper");
    }
}
