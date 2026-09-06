"""Deterministic canonical serialization for the evidence bundle (Stage 3, S7).

Re-verification has to reproduce the exact bytes a bundle was hashed from,
on a different machine, possibly years later.  Two things break that in
practice:

* **Bare floats.**  ``repr(0.1)`` is not portable and ``json`` will happily
  emit ``0.30000000000000004``.  Every number that enters the bundle must
  first pass through :func:`q`, which renders a fixed-precision *string*.
* **Key order / whitespace.**  ``json.dumps`` defaults are not canonical.

:func:`canon` therefore rejects raw floats and non-string keys outright,
sorts keys, uses the most compact separators, and encodes as UTF-8.  The
output is the pre-image of every Merkle leaf in :mod:`faceproof.merkle`.

This mirrors Person 1's ``handoff.q`` / ``_reject_floats`` exactly (same
default precision, same rejection rule) so a value formatted in Stage 1
survives into Stage 3 unchanged.
"""

from __future__ import annotations

import json
from typing import Any

# Fixed-precision default.  Kept identical to ``config.float_precision`` /
# ``handoff.q`` so Stage 1 and Stage 3 format numbers the same way.
DEFAULT_PRECISION = 6


def q(x: Any, nd: int = DEFAULT_PRECISION) -> str:
    """Quantise a number to a fixed-precision decimal *string* (D9).

    ``q(0.1234567) == "0.123457"``.  Accepts anything ``float()`` accepts,
    including ints and numeric strings, and always returns a string so the
    value can go straight into :func:`canon` without tripping the float
    rejection.
    """
    return f"{float(x):.{nd}f}"


def _reject_floats(o: Any, path: str = "$") -> None:
    """Recursively fail if a bare float or non-string mapping key survived.

    Do not weaken this.  A float that reaches the bundle is the single most
    common cause of "verification passes locally, fails on another machine".
    """
    if isinstance(o, float):
        raise TypeError(
            f"raw float at {path} - every number must go through q() first"
        )
    if isinstance(o, dict):
        for k, v in o.items():
            if not isinstance(k, str):
                raise TypeError(
                    f"non-string mapping key at {path}: {k!r} ({type(k).__name__})"
                )
            _reject_floats(v, f"{path}.{k}")
    elif isinstance(o, (list, tuple)):
        for i, v in enumerate(o):
            _reject_floats(v, f"{path}[{i}]")


def canon(o: Any) -> bytes:
    """Return the deterministic canonical JSON encoding of ``o``.

    * raw floats and non-string keys are rejected
    * keys are sorted lexicographically
    * separators are ``","`` / ``":"`` (no whitespace)
    * UTF-8, ``ensure_ascii=False`` (real characters, not ``\\uXXXX``)

    The bytes are reproducible: ``canon(x) == canon(x)`` across processes
    and machines, which is the whole point.
    """
    _reject_floats(o)
    return json.dumps(
        o,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
