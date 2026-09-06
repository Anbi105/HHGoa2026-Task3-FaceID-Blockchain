from faceproof.merkle import MerkleTree, verify
def fields(): return [{"value":str(i)} for i in range(8)]
def test_eight_leaves_and_all_proofs():
    tree=MerkleTree(fields())
    for i, leaf in enumerate(tree.leaves): assert verify(leaf,tree.proof(i),tree.root)
def test_modified_leaf_is_invalid():
    tree=MerkleTree(fields()); other=MerkleTree([{ "value":"changed"}]+fields()[1:])
    assert not verify(other.leaves[0],tree.proof(0),tree.root)
def test_deterministic_root(): assert MerkleTree(fields()).root == MerkleTree(fields()).root
