from __future__ import annotations

import hashlib
import logging
from types import SimpleNamespace

import pytest

from app.core import email as email_service
from app.core import hibp
from app.routers import admin
from scripts import seed_account


@pytest.mark.asyncio
async def test_email_fallback_logs_no_recipient_or_token(monkeypatch, caplog):
    monkeypatch.setattr(email_service.settings, "resend_api_key", None)
    token = "sensitive-reset-token"
    recipient = "patient@example.org"

    with caplog.at_level(logging.WARNING, logger="app.email"):
        await email_service._send(
            recipient,
            "Reset your MetaHarmonizer password",
            f'<a href="https://example.org/reset?token={token}">Reset</a>',
        )

    assert "delivery skipped" in caplog.text.lower()
    assert token not in caplog.text
    assert recipient not in caplog.text
    assert "https://" not in caplog.text


@pytest.mark.asyncio
async def test_seed_account_never_prints_password(monkeypatch, capsys):
    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def commit(self):
            return None

    async def get_by_email(_db, _email):
        return None

    async def count_users(_db):
        return 0

    async def create_user(_db, **values):
        return SimpleNamespace(role=values["role"])

    async def set_email_verified(_db, _user):
        return None

    monkeypatch.setattr(seed_account, "SessionLocal", Session)
    monkeypatch.setattr(seed_account, "hash_password", lambda _password: "hash")
    monkeypatch.setattr(seed_account.users_repo, "get_by_email", get_by_email)
    monkeypatch.setattr(seed_account.users_repo, "count_users", count_users)
    monkeypatch.setattr(seed_account.users_repo, "create_user", create_user)
    monkeypatch.setattr(seed_account.users_repo, "set_email_verified", set_email_verified)

    password = "never-print-this-password"
    await seed_account.seed("admin@example.org", password, None, "admin")

    output = capsys.readouterr().out
    assert "Account created" in output
    assert password not in output


def test_schema_upload_path_is_generated_inside_store(monkeypatch, tmp_path):
    monkeypatch.setattr(admin, "SCHEMA_STORE", tmp_path)

    first = admin._new_schema_upload_path()
    second = admin._new_schema_upload_path()

    assert first.parent == tmp_path
    assert second.parent == tmp_path
    assert first != second
    assert first.name.startswith("curated_")
    assert first.suffix == ".csv"


@pytest.mark.asyncio
async def test_hibp_sends_only_sha1_prefix(monkeypatch):
    password = "correct horse battery staple"
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    requested: list[tuple[str, dict[str, str]]] = []

    class Response:
        status_code = 200
        text = f"{digest[5:]}:3\n"

    class Client:
        def __init__(self, *, timeout):
            assert timeout == 2.5

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, *, headers):
            requested.append((url, headers))
            return Response()

    monkeypatch.setattr(hibp.httpx, "AsyncClient", Client)

    assert await hibp.password_breach_count(password) == 3
    assert requested == [(f"{hibp._API}{digest[:5]}", {"Add-Padding": "true"})]
    assert password not in requested[0][0]
    assert digest not in requested[0][0]
