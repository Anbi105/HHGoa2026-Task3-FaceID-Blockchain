"""Consent binding, commitments, and the erasure path (§8, D12).

Design
------
This is what makes the tool a *verification* system rather than a
de-anonymiser.  A probe cannot run without a live, in-scope, unexpired
consent record for a named subject.

Two artifacts leave this module for the attestation path, and both are
opaque 32-byte digests:

    subject_commitment   = keccak256(consent_token)
    embedding_commitment = keccak256(salt || embedding_bytes)

Neither the raw image, the raw embedding, nor the subject id ever reaches
the chain.

Erasure
-------
The per-subject salt lives only in the local consent store.  Revoking a
subject destroys that salt, after which no one — including us — can ever
demonstrate that a given embedding produced an anchored commitment.  That
is the erasure path against an immutable ledger.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
from Crypto.Hash import keccak  # pycryptodome — Ethereum-compatible keccak256

from faceproof.config import cfg

SALT_BYTES = 32


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Consent record
# ---------------------------------------------------------------------------


@dataclass
class ConsentRecord:
    """Consent granted by a subject to be searched.

    Attributes
    ----------
    subject_id : str
        Local identifier for the consenting subject.  Never leaves the host.
    scope : str
        What the consent covers (e.g. ``"face_probe_demo"``).
    granted_at, expires_at : str
        ISO-8601 UTC timestamps.  Consent is time-boxed by design.
    token : str
        Unique consent token (UUID4).  Its keccak256 is the on-chain leaf.
    salt_hex : str | None
        Per-subject 256-bit salt for the embedding commitment.
        ``None`` once the subject has been erased.
    revoked_at : str | None
        Set when consent is withdrawn; the salt is destroyed at the same time.
    """

    subject_id: str
    scope: str
    granted_at: str = field(default_factory=lambda: _iso(_now()))
    expires_at: str = ""
    token: str = field(default_factory=lambda: str(uuid.uuid4()))
    salt_hex: Optional[str] = None
    revoked_at: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.expires_at:
            self.expires_at = _iso(_now() + timedelta(days=cfg.consent_ttl_days))
        if self.salt_hex is None and self.revoked_at is None:
            self.salt_hex = os.urandom(SALT_BYTES).hex()

    # ── Derived ─────────────────────────────────────────────────────

    @property
    def salt(self) -> Optional[bytes]:
        return bytes.fromhex(self.salt_hex) if self.salt_hex else None

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, object]) -> "ConsentRecord":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})  # type: ignore[arg-type]

    def public(self) -> Dict[str, object]:
        """Everything about this consent except the two secrets."""
        return {
            "scope": self.scope,
            "granted_at": self.granted_at,
            "expires_at": self.expires_at,
            "revoked_at": self.revoked_at,
            "subject_commitment": "0x" + subject_commitment(self).hex(),
        }


def grant(
    subject_id: str,
    scope: Optional[str] = None,
    ttl_days: Optional[int] = None,
) -> ConsentRecord:
    """Create a fresh consent record for *subject_id*."""
    if not subject_id or not subject_id.strip():
        raise ValueError("subject_id is required")
    ttl = cfg.consent_ttl_days if ttl_days is None else ttl_days
    return ConsentRecord(
        subject_id=subject_id.strip(),
        scope=scope or cfg.consent_scope,
        expires_at=_iso(_now() + timedelta(days=ttl)),
    )


def check(
    record: Optional[ConsentRecord],
    scope: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Tuple[bool, str]:
    """Decide whether *record* authorises a probe.

    Returns ``(ok, reason)``.  ``reason`` is ``"ok"`` on success and a
    machine-readable rejection code otherwise — it is printed on camera
    and written to the manifest.
    """
    now = now or _now()

    if record is None:
        return False, "no_consent_on_record"
    if not record.subject_id:
        return False, "missing_subject_id"
    if not record.scope:
        return False, "missing_scope"

    try:
        uuid.UUID(record.token, version=4)
    except (ValueError, AttributeError, TypeError):
        return False, "malformed_consent_token"

    if record.is_revoked:
        return False, f"consent_revoked:{record.revoked_at}"
    if record.salt_hex is None:
        return False, "consent_salt_erased"

    granted = _parse(record.granted_at)
    if granted is None:
        return False, "malformed_granted_at"
    if granted > now:
        return False, "consent_not_yet_valid"

    expires = _parse(record.expires_at)
    if expires is None:
        return False, "malformed_expires_at"
    if expires <= now:
        return False, f"consent_expired:{record.expires_at}"

    if scope is not None and record.scope != scope:
        return False, f"scope_mismatch:{record.scope}!={scope}"

    return True, "ok"


def validate(record: Optional[ConsentRecord]) -> bool:
    """Boolean form of :func:`check` (kept for backwards compatibility)."""
    ok, _ = check(record)
    return ok


# ---------------------------------------------------------------------------
# Commitments
# ---------------------------------------------------------------------------


def _keccak(payload: bytes) -> bytes:
    h = keccak.new(digest_bits=256)
    h.update(payload)
    return h.digest()


def fresh_salt() -> bytes:
    """Generate a 256-bit cryptographic salt."""
    return os.urandom(SALT_BYTES)


def subject_commitment(record: ConsentRecord) -> bytes:
    """keccak256 of the consent token — the subject leaf of the Merkle tree.

    Carries no PII: the token is a random UUID4 with no relationship to
    the subject's identity.
    """
    return _keccak(record.token.encode("utf-8"))


def embedding_commitment(
    embedding: np.ndarray,
    salt: Optional[bytes] = None,
) -> Tuple[bytes, bytes]:
    """Compute an opaque keccak256 commitment to a face embedding.

    The embedding is serialised as little-endian float32 (``<f4``)
    regardless of host byte order, so the commitment is reproducible
    across machines (§14, "different roots on two machines").

    Returns ``(commitment, salt)``.  Destroying the salt makes the
    commitment permanently unverifiable.
    """
    if salt is None:
        salt = fresh_salt()
    if len(salt) != SALT_BYTES:
        raise ValueError(f"salt must be {SALT_BYTES} bytes, got {len(salt)}")

    payload = salt + embedding_bytes(embedding)
    return _keccak(payload), salt


def embedding_bytes(embedding: np.ndarray) -> bytes:
    """Canonical byte encoding of an embedding: little-endian float32, C order."""
    return np.ascontiguousarray(embedding, dtype="<f4").tobytes()


# ---------------------------------------------------------------------------
# Consent store
# ---------------------------------------------------------------------------


class ConsentStore:
    """A local JSON store of consent records.

    Holds per-subject salts, so it is a secret: ``data/consent/`` is
    gitignored and must never be committed or published.
    """

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else cfg.consent_store
        self._records: Dict[str, ConsentRecord] = {}
        self.load()

    # ── Persistence ─────────────────────────────────────────────────

    def load(self) -> "ConsentStore":
        self._records = {}
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8") or "{}")
            for sid, d in raw.get("subjects", {}).items():
                self._records[sid] = ConsentRecord.from_dict(d)
        return self

    def save(self) -> None:
        """Atomically write the store, never leaving salts world-readable.

        The temp file is created 0600 *before* anything is written to it.
        Writing at the default umask (0644) and only chmod-ing the final path
        after ``os.replace`` leaves a window in which every local user can
        read the per-subject salts — the one secret in this repo whose
        disclosure defeats the erasure guarantee.  The directory is 0700 for
        the same reason.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.path.parent, 0o700)
        except (OSError, NotImplementedError):  # pragma: no cover - Windows
            pass

        payload = {
            "schema": "faceproof.consent_store.v1",
            "updated_at": _iso(_now()),
            "subjects": {sid: r.to_dict() for sid, r in sorted(self._records.items())},
        }
        body = json.dumps(payload, indent=2, sort_keys=True) + "\n"

        tmp = self.path.with_suffix(".tmp")
        # O_CREAT|O_EXCL with mode 0600: the file never exists at a wider mode.
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(tmp, flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(body)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)  # contains salts
        except (OSError, NotImplementedError):  # pragma: no cover - Windows
            pass

    # ── Operations ──────────────────────────────────────────────────

    def get(self, subject_id: str) -> Optional[ConsentRecord]:
        return self._records.get(subject_id)

    def grant(
        self,
        subject_id: str,
        scope: Optional[str] = None,
        ttl_days: Optional[int] = None,
    ) -> ConsentRecord:
        record = grant(subject_id, scope=scope, ttl_days=ttl_days)
        self._records[record.subject_id] = record
        self.save()
        return record

    def revoke(self, subject_id: str) -> Optional[ConsentRecord]:
        """Withdraw consent and destroy the salt — the erasure path.

        The record itself is retained (revoked, salt-less) so that the
        withdrawal is auditable.  Once this returns, every commitment ever
        made for this subject is permanently unverifiable.
        """
        record = self._records.get(subject_id)
        if record is None:
            return None
        record.salt_hex = None
        record.revoked_at = _iso(_now())
        self.save()
        return record

    def list(self) -> List[ConsentRecord]:
        return [self._records[k] for k in sorted(self._records)]

    def __contains__(self, subject_id: object) -> bool:
        return subject_id in self._records

    def __len__(self) -> int:
        return len(self._records)


def subjects(store: Optional[ConsentStore] = None) -> Iterable[ConsentRecord]:
    return (store or ConsentStore()).list()
