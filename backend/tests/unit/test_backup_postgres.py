from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from cryptography.exceptions import InvalidTag

from scripts import backup_postgres as backup


def _name(stamp: datetime) -> str:
    return f"postgres/metaharmonizer/metaharmonizer-{stamp.strftime('%Y%m%dT%H%M%SZ')}.dump.enc"


def test_encrypt_decrypt_round_trip(tmp_path):
    source = tmp_path / "source.dump"
    encrypted = tmp_path / "source.dump.enc"
    restored = tmp_path / "restored.dump"
    source.write_bytes((b"postgres-data\0" * 100_000) + b"end")
    key = bytes(range(32))

    digest = backup.encrypt_file(source, encrypted, key)
    backup.decrypt_file(encrypted, restored, key)

    assert restored.read_bytes() == source.read_bytes()
    assert len(digest) == 64
    assert source.read_bytes() not in encrypted.read_bytes()


def test_tampered_backup_is_rejected(tmp_path):
    source = tmp_path / "source.dump"
    encrypted = tmp_path / "source.dump.enc"
    restored = tmp_path / "restored.dump"
    source.write_bytes(b"database")
    key = bytes(range(32))
    backup.encrypt_file(source, encrypted, key)
    damaged = bytearray(encrypted.read_bytes())
    damaged[-backup.TAG_SIZE - 1] ^= 1
    encrypted.write_bytes(damaged)

    with pytest.raises(InvalidTag):
        backup.decrypt_file(encrypted, restored, key)


def test_restore_sql_removes_only_unsupported_transaction_timeout(tmp_path):
    source = tmp_path / "raw.sql"
    destination = tmp_path / "restore.sql"
    source.write_bytes(
        b"SET statement_timeout = 0;\n"
        b"SET transaction_timeout = 0;\n"
        b"SET lock_timeout = 0;\n"
        b"SELECT 'SET transaction_timeout = 0;';\n"
    )

    removed = backup._write_compatible_restore_sql(source, destination)

    assert removed == 1
    assert destination.read_bytes() == (
        b"SET statement_timeout = 0;\n"
        b"SET lock_timeout = 0;\n"
        b"SELECT 'SET transaction_timeout = 0;';\n"
    )


def test_retention_keeps_daily_weekly_monthly_tiers():
    now = datetime(2026, 8, 8, 2, tzinfo=timezone.utc)
    keys = [_name(now - timedelta(days=day)) for day in range(400)]

    kept = backup.retention_keys(keys)

    daily = {_name(now - timedelta(days=day)) for day in range(7)}
    assert daily <= kept
    assert len(kept) <= 23
    assert any("202509" in key for key in kept)


def test_restore_refuses_production_database(monkeypatch):
    url = "postgresql+asyncpg://mh:secret@postgres:5432/metaharmonizer"
    monkeypatch.setenv("DATABASE_URL", url)

    with pytest.raises(RuntimeError, match="refusing"):
        backup.restore(url, "postgres/example.dump.enc", allow_production=False)