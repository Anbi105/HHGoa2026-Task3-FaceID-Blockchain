"""FaceProof — Stage 1 probe for HH Goa 2026 Task 3.

Public API (the Stage 2 contract)
---------------------------------
    from faceproof import encode, Probe, Rejection, cosine
    from faceproof import ConsentStore, ConsentRecord
    from faceproof.handoff import load_record, read_embedding

These names are resolved **lazily** (PEP 562).  Importing them pulls in the
face stack — ``consent`` needs numpy, ``face`` needs cv2 — and that used to
happen on ``import faceproof`` alone, which meant a third party could not
``import faceproof.merkle`` to re-verify a bundle without installing
OpenCV and InsightFace first.  Re-verification is the whole point of the
attestation, so the crypto core stays importable on its own:

    pip install "faceproof[verify]"      # no model stack
    python -m faceproof.verify_cli out/run-<id>

Touching ``faceproof.encode`` (or any other name below) still imports the
face stack exactly as before.
"""

from typing import TYPE_CHECKING

__version__ = "1.1.0"

# name -> submodule it lives in
_LAZY = {
    "ConsentRecord": "faceproof.consent",
    "ConsentStore": "faceproof.consent",
    "embedding_commitment": "faceproof.consent",
    "subject_commitment": "faceproof.consent",
    "grant_consent": "faceproof.consent",
    "Probe": "faceproof.face",
    "Rejection": "faceproof.face",
    "cosine": "faceproof.face",
    "encode": "faceproof.face",
}

# ``grant_consent`` is exported under a different name than it is defined
_ALIASES = {"grant_consent": "grant"}

__all__ = sorted(_LAZY) + ["__version__"]


def __getattr__(name: str):
    """Import the owning submodule only when the name is actually used."""
    module_path = _LAZY.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(module_path)
    value = getattr(module, _ALIASES.get(name, name))
    globals()[name] = value          # cache: only the first access pays
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY))


if TYPE_CHECKING:  # pragma: no cover - type checkers want the real symbols
    from faceproof.consent import (  # noqa: F401
        ConsentRecord,
        ConsentStore,
        embedding_commitment,
        grant as grant_consent,
        subject_commitment,
    )
    from faceproof.face import Probe, Rejection, cosine, encode  # noqa: F401
