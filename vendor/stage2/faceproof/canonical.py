"""The sole cryptographic serialization path. Floats are prohibited by design."""
import json
from decimal import Decimal

def _normalise(value):
    if isinstance(value, float):
        raise TypeError("cryptographic evidence numbers must be fixed-precision strings")
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {str(k): _normalise(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalise(v) for v in value]
    return value

def canonical_bytes(value) -> bytes:
    return json.dumps(_normalise(value), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
