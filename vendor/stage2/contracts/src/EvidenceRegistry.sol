// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

contract EvidenceRegistry {
    error ZeroRoot(); error DuplicateRoot(bytes32 root);
    struct Anchor { bytes32 root; string schema; string uri; address submitter; uint256 timestamp; }
    Anchor[] private anchors;
    mapping(bytes32 => uint256) private idPlusOne;
    event Anchored(uint256 indexed id, bytes32 indexed root, string schema, string uri, address indexed submitter);
    function anchor(bytes32 root, string calldata schema, string calldata uri) external returns (uint256 id) {
        if (root == bytes32(0)) revert ZeroRoot(); if (idPlusOne[root] != 0) revert DuplicateRoot(root);
        id=anchors.length; anchors.push(Anchor(root,schema,uri,msg.sender,block.timestamp)); idPlusOne[root]=id+1;
        emit Anchored(id,root,schema,uri,msg.sender);
    }
    function idOf(bytes32 root) external view returns (uint256) { uint256 x=idPlusOne[root]; require(x != 0, "unknown root"); return x-1; }
    function get(uint256 id) external view returns (Anchor memory) { return anchors[id]; }
    function verifyField(uint256 id, bytes32 leaf, bytes32[] calldata proof) external view returns (bool) {
        bytes32 current=leaf; for(uint i;i<proof.length;i++) current=keccak256(abi.encodePacked(current < proof[i] ? current : proof[i], current < proof[i] ? proof[i] : current)); return current==anchors[id].root;
    }
}
