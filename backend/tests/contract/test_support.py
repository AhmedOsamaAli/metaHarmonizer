from __future__ import annotations

import uuid

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.core.settings as settings_mod
import app.db.session as db_session
from app.core.storage import LocalStorage
from app.db.models import User

from _authflow import register_and_login

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def env(database_url, monkeypatch, tmp_path):
    engine = create_async_engine(database_url, poolclass=sa.pool.NullPool)
    db_session.engine = engine
    db_session.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    domain = f"support-{uuid.uuid4().hex[:8]}.example.com"
    monkeypatch.setattr(settings_mod.settings, "allowed_email_domains", domain)
    monkeypatch.setattr(settings_mod.settings, "hibp_check", False)

    from fastapi import FastAPI
    from app.core.middleware import install_observability
    from app.routers import auth, support

    emails: list[tuple[str, str]] = []

    async def confirmation(**kwargs):
        emails.append(("confirmation", kwargs["to"]))

    async def admin_notice(**kwargs):
        emails.append(("admin", kwargs["to"]))

    async def update_notice(**kwargs):
        emails.append(("update", kwargs["to"]))

    monkeypatch.setattr(support, "get_storage", lambda: LocalStorage(tmp_path / "objects"))
    monkeypatch.setattr(support, "send_support_ticket_confirmation", confirmation)
    monkeypatch.setattr(support, "send_admin_support_ticket_email", admin_notice)
    monkeypatch.setattr(support, "send_support_update_email", update_notice)

    app = FastAPI()
    install_observability(app)
    app.include_router(auth.router)
    app.include_router(support.router)

    def client():
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    yield client, domain, emails

    async with db_session.SessionLocal() as db:
        await db.execute(sa.delete(User).where(User.email.like(f"%@{domain}")))
        await db.commit()
    await engine.dispose()


async def test_support_ticket_role_flow_and_screenshot(env):
    make_client, domain, emails = env
    async with make_client() as client:
        admin = await register_and_login(client, f"admin@{domain}")
        curator = await register_and_login(client, f"curator@{domain}")
        outsider = await register_and_login(client, f"other@{domain}")
        admin_h = {"Authorization": f"Bearer {admin['access_token']}"}
        curator_h = {"Authorization": f"Bearer {curator['access_token']}"}
        outsider_h = {"Authorization": f"Bearer {outsider['access_token']}"}

        png = b"\x89PNG\r\n\x1a\n" + b"test-image"
        created = await client.post(
            "/api/v1/support",
            headers=curator_h,
            data={
                "category": "bug",
                "subject": "Review page issue",
                "description": "The mapping review page does not show the expected row.",
            },
            files={"screenshot": ("screen.png", png, "image/png")},
        )
        assert created.status_code == 201, created.text
        ticket = created.json()
        ticket_id = ticket["id"]
        assert ticket["has_screenshot"] is True
        assert ticket["status"] == "open"
        assert ("confirmation", f"curator@{domain}") in emails
        assert ("admin", f"admin@{domain}") in emails

        assert (
            await client.get(f"/api/v1/support/{ticket_id}", headers=outsider_h)
        ).status_code == 404
        admin_list = await client.get("/api/v1/support", headers=admin_h)
        assert any(row["id"] == ticket_id for row in admin_list.json())

        screenshot = await client.get(
            f"/api/v1/support/{ticket_id}/screenshot", headers=admin_h
        )
        assert screenshot.status_code == 200
        assert screenshot.content == png
        assert screenshot.headers["content-type"].startswith("image/png")

        replied = await client.post(
            f"/api/v1/support/{ticket_id}/replies",
            headers=admin_h,
            json={"body": "Thanks, we are investigating this now."},
        )
        assert replied.status_code == 200
        assert replied.json()["status"] == "in_progress"
        assert replied.json()["replies"][0]["author_role"] == "admin"
        assert ("update", f"curator@{domain}") in emails

        resolved = await client.patch(
            f"/api/v1/support/{ticket_id}",
            headers=admin_h,
            json={"status": "resolved"},
        )
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "resolved"
        assert (
            await client.patch(
                f"/api/v1/support/{ticket_id}",
                headers=curator_h,
                json={"status": "resolved"},
            )
        ).status_code == 403

        admin_ticket = await client.post(
            "/api/v1/support",
            headers=admin_h,
            data={
                "category": "question",
                "subject": "Admin support question",
                "description": "An administrator also needs access to the support workflow.",
            },
        )
        assert admin_ticket.status_code == 201
        assert admin_ticket.json()["creator_role"] == "admin"
