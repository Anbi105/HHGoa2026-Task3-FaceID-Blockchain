from eth_utils import keccak
from .canonical import canonical_bytes

def _h(data: bytes) -> bytes: return keccak(data)
def leaf(value) -> bytes: return _h(_h(canonical_bytes(value)))
def pair(left: bytes, right: bytes) -> bytes: return _h(min(left, right) + max(left, right))

class MerkleTree:
    def __init__(self, fields):
        if len(fields) != 8: raise ValueError("evidence must have exactly eight field groups")
        self.leaves = [leaf(x) for x in fields]
        self.levels = [self.leaves]
        while len(self.levels[-1]) > 1:
            current = self.levels[-1]
            self.levels.append([pair(current[i], current[i+1]) for i in range(0, len(current), 2)])
    @property
    def root(self): return self.levels[-1][0]
    def proof(self, index):
        if not 0 <= index < 8: raise IndexError(index)
        result=[]
        for level in self.levels[:-1]:
            result.append(level[index ^ 1]); index //=2
        return result

def verify(leaf_hash, proof, root):
    current=leaf_hash
    for sibling in proof: current=pair(current, sibling)
    return current == root

def hex0(value): return "0x" + value.hex()
