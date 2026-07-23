"""Federation signing hardening (G1):
  - key rotation: multiple trusted keys per peer both verify (overlap window);
  - replay defense: stale / future-dated / undated bundles are rejected.

Pure-crypto unit tests — no DB, no HTTP.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.settings import settings
from app.services import federation as fed


def _pub_hex(priv: Ed25519PrivateKey) -> str:
    return priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()


def _sign(priv: Ed25519PrivateKey, payload: dict) -> str:
    return priv.sign(fed.canonical_bytes(payload)).hex()


def _payload(**extra) -> dict:
    p = {"source_instance": "peerX", "created_at": datetime.now(timezone.utc).isoformat(), "mappings": []}
    p.update(extra)
    return p


def test_rotation_accepts_old_and_new_keys(monkeypatch):
    old, new, other = (Ed25519PrivateKey.generate() for _ in range(3))
    monkeypatch.setattr(
        settings, "federation_trusted_keys",
        f"peerX:{_pub_hex(old)},peerX:{_pub_hex(new)}",
    )
    payload = _payload()
    assert fed.verify_payload(payload, _sign(old, payload), "peerX") is True
    assert fed.verify_payload(payload, _sign(new, payload), "peerX") is True
    # A key not registered for the peer must not verify.
    assert fed.verify_payload(payload, _sign(other, payload), "peerX") is False


def test_unknown_source_rejected(monkeypatch):
    monkeypatch.setattr(settings, "federation_trusted_keys", "")
    priv = Ed25519PrivateKey.generate()
    payload = _payload(source_instance="ghost")
    assert fed.verify_payload(payload, _sign(priv, payload), "ghost") is False


def test_freshness_accepts_recent():
    fed.check_freshness(_payload())  # no raise


def test_freshness_rejects_stale(monkeypatch):
    monkeypatch.setattr(settings, "federation_max_bundle_age_days", 30)
    old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    with pytest.raises(ValueError, match="older than"):
        fed.check_freshness({"created_at": old})


def test_freshness_rejects_future(monkeypatch):
    monkeypatch.setattr(settings, "federation_clock_skew_min", 5)
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError, match="future"):
        fed.check_freshness({"created_at": future})


def test_freshness_rejects_missing():
    with pytest.raises(ValueError, match="missing"):
        fed.check_freshness({})


def test_freshness_age_bound_disabled(monkeypatch):
    monkeypatch.setattr(settings, "federation_max_bundle_age_days", 0)
    old = (datetime.now(timezone.utc) - timedelta(days=3650)).isoformat()
    fed.check_freshness({"created_at": old})  # no raise when disabled
