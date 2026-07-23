"""Federation-lite signing + payload helpers (G1).

Two deploying institutions exchange a signed JSON bundle of curator-confirmed
mappings. This module owns the cryptography:

  - a per-instance Ed25519 keypair (private seed from settings, dev fallback);
  - deterministic canonical JSON so signatures are stable across machines;
  - sign / verify against a trusted-peer public-key registry.

It does NOT touch the database — the repository + router compose it with
persistence and the two-stage approval flow (Q10).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.core.settings import settings

BUNDLE_VERSION = 1


# Canonical serialization (stable bytes for signing/hashing)
def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """Deterministic UTF-8 JSON: sorted keys, no whitespace.

    Signing and verification must hash identical bytes on both instances, so the
    serialization can't depend on dict order or platform whitespace.
    """
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def payload_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


# Keys
def _private_key() -> Ed25519PrivateKey:
    """This instance's signing key.

    Uses ``FEDERATION_PRIVATE_KEY`` (hex 32-byte seed) when set. Otherwise
    derives a deterministic dev key from the instance id so local two-instance
    round-trips work without configuration — never use the fallback in
    production (a peer could forge this instance's signature).
    """
    hex_seed = settings.federation_private_key
    if hex_seed:
        seed = bytes.fromhex(hex_seed.strip())
    else:
        if settings.is_production_like:
            raise RuntimeError(
                "FEDERATION_PRIVATE_KEY is not set. Federation requires a real "
                "Ed25519 key in production — the derived dev key is guessable."
            )
        seed = hashlib.sha256(
            f"mh-fed-dev::{settings.federation_instance_id}".encode()
        ).digest()
    return Ed25519PrivateKey.from_private_bytes(seed[:32])


def public_key_hex() -> str:
    """This instance's public key (hex) — share it with peers to be trusted."""
    from cryptography.hazmat.primitives import serialization

    raw = _private_key().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return raw.hex()


def _trusted_keys() -> dict[str, list[Ed25519PublicKey]]:
    """Parse ``FEDERATION_TRUSTED_KEYS`` into ``{instance_id: [public_key, ...]}``.

    Multiple entries for the same instance are all kept, so a peer can publish a
    new key alongside its old one during rotation and both verify. This instance
    always trusts itself (so a local export/import round-trip and tests work out
    of the box).
    """
    out: dict[str, list[Ed25519PublicKey]] = {
        settings.federation_instance_id: [_private_key().public_key()]
    }
    raw = settings.federation_trusted_keys or ""
    for item in raw.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        instance_id, hex_key = item.split(":", 1)
        try:
            key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(hex_key.strip()))
        except (ValueError, Exception):  # noqa: BLE001 — skip malformed entries
            continue
        out.setdefault(instance_id.strip(), []).append(key)
    return out


# ---------------------------------------------------------------------------
# Sign / verify
# ---------------------------------------------------------------------------
def sign_payload(payload: dict[str, Any]) -> str:
    """Return a hex Ed25519 signature over the canonical payload bytes."""
    return _private_key().sign(canonical_bytes(payload)).hex()


def verify_payload(payload: dict[str, Any], signature_hex: str, source_instance: str) -> bool:
    """Verify ``signature_hex`` over ``payload`` against the source's trusted keys.

    Accepts the signature if it matches ANY key registered for the source, so a
    key rotation with an overlap window works. Returns False on an unknown
    source, a malformed signature, or no match — never raises, so the import
    path can record the result and reject cleanly.
    """
    keys = _trusted_keys().get(source_instance)
    if not keys:
        return False
    try:
        signature = bytes.fromhex(signature_hex)
    except ValueError:
        return False
    data = canonical_bytes(payload)
    for key in keys:
        try:
            key.verify(signature, data)
            return True
        except InvalidSignature:
            continue
    return False


def bundle_created_at(payload: dict[str, Any]) -> datetime | None:
    """Parse the bundle's signed ``created_at`` (ISO-8601) as an aware UTC datetime."""
    raw = payload.get("created_at")
    if not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def check_freshness(payload: dict[str, Any]) -> None:
    """Reject a stale or future-dated bundle (replay defense).

    ``created_at`` is part of the signed payload, so an attacker can't backdate a
    replayed bundle without breaking the signature. Raises ``ValueError`` when
    the timestamp is missing/unparseable, too far in the future, or older than
    ``federation_max_bundle_age_days`` (0 disables the age bound).
    """
    dt = bundle_created_at(payload)
    if dt is None:
        raise ValueError("Bundle 'created_at' is missing or unparseable.")
    now = datetime.now(timezone.utc)
    if dt > now + timedelta(minutes=settings.federation_clock_skew_min):
        raise ValueError("Bundle is future-dated.")
    max_age = settings.federation_max_bundle_age_days
    if max_age and now - dt > timedelta(days=max_age):
        raise ValueError(f"Bundle is older than {max_age} days (possible replay).")
