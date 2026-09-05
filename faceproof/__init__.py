"""FaceProof — Stage 1 probe for HH Goa 2026 Task 3.

Public API (the Stage 2 contract)
---------------------------------
    from faceproof import encode, Probe, Rejection, cosine
    from faceproof import ConsentStore, ConsentRecord
    from faceproof.handoff import load_record, read_embedding
"""

from faceproof.consent import (  # noqa: F401
    ConsentRecord,
    ConsentStore,
    embedding_commitment,
    grant as grant_consent,
    subject_commitment,
)
from faceproof.face import Probe, Rejection, cosine, encode  # noqa: F401

__version__ = "1.1.0"
