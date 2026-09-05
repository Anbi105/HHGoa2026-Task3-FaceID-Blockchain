import json
from pathlib import Path
from eth_utils import keccak
from .canonical import canonical_bytes

def load_consent(path: str | Path):
    record=json.loads(Path(path).read_text(encoding="utf-8"))
    required={"subject_id", "scope", "granted_at", "token"}
    if required - record.keys(): raise ValueError("invalid consent record")
    return record
def commitment(record): return "0x" + keccak(canonical_bytes(record)).hex()
