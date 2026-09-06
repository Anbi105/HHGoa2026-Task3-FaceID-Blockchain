// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/**
 * @title  MerkleLite
 * @notice Sorted-pair keccak256 Merkle verification, byte-for-byte compatible
 *         with `faceproof/merkle.py`.
 * @dev    Leaves are hashed off-chain as keccak256(keccak256(canonical_group)).
 *         Internal nodes are keccak256(min(a,b) || max(a,b)) so a proof needs
 *         only sibling hashes, no direction bits.
 */
library MerkleLite {
    function processProof(bytes32 leaf, bytes32[] calldata proof)
        internal
        pure
        returns (bytes32 computed)
    {
        computed = leaf;
        for (uint256 i = 0; i < proof.length; ++i) {
            bytes32 sib = proof[i];
            computed = computed <= sib
                ? keccak256(abi.encodePacked(computed, sib))
                : keccak256(abi.encodePacked(sib, computed));
        }
    }

    function verify(bytes32 leaf, bytes32[] calldata proof, bytes32 root)
        internal
        pure
        returns (bool)
    {
        return processProof(leaf, proof) == root;
    }
}

/**
 * @title  EvidenceRegistry
 * @notice Append-only, ownerless registry for anchoring evidence-bundle Merkle
 *         roots (§14, §15).
 * @dev    No admin, no pause, no upgrade path. Stores only a 32-byte root, its
 *         schema id, a bundle URI, the submitter and a timestamp — never raw
 *         biometrics or other personal data.
 */
contract EvidenceRegistry {
    using MerkleLite for bytes32;

    error ZeroRoot();
    error RootAlreadyAnchored(bytes32 root, uint256 existingId);
    error UnknownAnchor(uint256 id);
    error BadProofLength(uint256 got, uint256 want);

    /// @dev The evidence bundle is exactly 8 group leaves -> a full tree of
    ///      depth 3, so every genuine group proof has exactly 3 siblings.
    uint256 internal constant GROUP_PROOF_LENGTH = 3;

    struct Record {
        bytes32 root;
        uint256 anchoredAt;
        address submitter;
        bytes32 schema;
        string bundleURI;
    }

    event Anchored(
        uint256 indexed id,
        bytes32 indexed root,
        bytes32 indexed schema,
        string bundleURI,
        address submitter,
        uint256 anchoredAt
    );

    Record[] private _records;
    // root => id + 1  (0 means "not anchored")
    mapping(bytes32 => uint256) private _idPlusOne;

    /**
     * @notice Append a new evidence root. Idempotency is by root: a root can be
     *         anchored exactly once, by anyone, forever.
     * @dev    Deliberately permissionless — but note what that does and does
     *         not give you. A root is a deterministic function of its bundle,
     *         so anyone who sees a bundle before it is anchored can anchor
     *         that root first; the honest submitter's transaction then reverts
     *         `RootAlreadyAnchored` and `submitter` records the front-runner.
     *         Nothing is forged (the evidence is unchanged and still verifies)
     *         but **first-anchor is not proof of authorship**. Binding
     *         authorship would require a signature over the root from a key
     *         committed inside the bundle; that is out of scope here and is
     *         documented in LIMITATIONS.md §16.
     * @param root      keccak Merkle root of the eight evidence groups.
     * @param schema    32-byte schema identifier (keccak of the schema string).
     * @param bundleURI Off-chain location of the full bundle (may be empty).
     * @return id       Zero-based, monotonically increasing anchor id.
     */
    function anchor(bytes32 root, bytes32 schema, string calldata bundleURI)
        external
        returns (uint256 id)
    {
        if (root == bytes32(0)) revert ZeroRoot();
        uint256 slot = _idPlusOne[root];
        if (slot != 0) revert RootAlreadyAnchored(root, slot - 1);

        id = _records.length;
        _records.push(
            Record({
                root: root,
                anchoredAt: block.timestamp,
                submitter: msg.sender,
                schema: schema,
                bundleURI: bundleURI
            })
        );
        _idPlusOne[root] = id + 1;

        emit Anchored(id, root, schema, bundleURI, msg.sender, block.timestamp);
    }

    /// @notice Number of anchored records.
    function total() external view returns (uint256) {
        return _records.length;
    }

    /// @notice Full record for `id`. Reverts `UnknownAnchor` if out of range.
    function get(uint256 id) external view returns (Record memory) {
        if (id >= _records.length) revert UnknownAnchor(id);
        return _records[id];
    }

    /// @notice Anchor id for a previously anchored `root`. Reverts if unknown.
    function idOf(bytes32 root) external view returns (uint256) {
        uint256 slot = _idPlusOne[root];
        if (slot == 0) revert UnknownAnchor(0);
        return slot - 1;
    }

    /// @notice True if `root` has been anchored.
    function isAnchored(bytes32 root) external view returns (bool) {
        return _idPlusOne[root] != 0;
    }

    /**
     * @notice Verify a selective-disclosure proof: that `leaf` is one of the
     *         eight group leaves committed by anchor `id`'s root.
     * @dev    Pure sorted-pair keccak; identical result to the Python verifier.
     *         The proof length is pinned to 3 so a shorter path cannot pass an
     *         internal node (or, at length 0, the root itself) off as a group
     *         leaf.
     */
    function verifyField(uint256 id, bytes32 leaf, bytes32[] calldata proof)
        external
        view
        returns (bool)
    {
        if (id >= _records.length) revert UnknownAnchor(id);
        if (proof.length != GROUP_PROOF_LENGTH) {
            revert BadProofLength(proof.length, GROUP_PROOF_LENGTH);
        }
        return leaf.verify(proof, _records[id].root);
    }
}
