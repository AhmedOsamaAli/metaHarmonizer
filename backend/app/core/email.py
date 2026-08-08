"""
Transactional email (verification + password reset) via Resend.

Sending is best-effort and isolated here so routers don't touch HTTP/email
details. When ``RESEND_API_KEY`` is set, mail goes out through Resend's REST
API. When it is unset, delivery is skipped and only a token-free status message
is logged. Local development can use the bootstrap/seed account without email.
"""

from __future__ import annotations

import logging

import httpx

from app.core.settings import settings

logger = logging.getLogger("app.email")

RESEND_ENDPOINT = "https://api.resend.com/emails"


async def _send(to: str, subject: str, html: str) -> None:
    """Send one email via Resend, or log a token-free status message."""
    if not settings.resend_api_key:
        logger.warning(
            "Email delivery skipped because RESEND_API_KEY is not configured "
            "(subject=%s)",
            subject,
        )
        return

    payload = {
        "from": settings.email_from,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    headers = {"Authorization": f"Bearer {settings.resend_api_key}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(RESEND_ENDPOINT, json=payload, headers=headers)
            resp.raise_for_status()
    except Exception:  # noqa: BLE001 — delivery failure must not break the request
        logger.exception("Resend delivery failed")


def _button(href: str, label: str) -> str:
    return (
        f'<a href="{href}" style="display:inline-block;padding:10px 18px;'
        f"background:#2986e2;color:#fff;border-radius:8px;text-decoration:none;"
        f'font-weight:600">{label}</a>'
    )


async def send_verification_email(*, to: str, name: str | None, token: str) -> None:
    link = f"{settings.app_base_url}/verify?token={token}"
    greeting = f"Hi {name}," if name else "Hi,"
    html = (
        f"<div style='font-family:system-ui,sans-serif;max-width:480px'>"
        f"<h2>Confirm your email</h2>"
        f"<p>{greeting}</p>"
        f"<p>Welcome to MetaHarmonizer. Please confirm your email address to "
        f"activate your account.</p>"
        f"<p>{_button(link, 'Verify email')}</p>"
        f"<p style='color:#64748b;font-size:13px'>This link expires in 24 hours. "
        f"If you didn't create an account, you can ignore this email.</p>"
        f"</div>"
    )
    await _send(
        to,
        "Confirm your MetaHarmonizer email",
        html,
    )


async def send_password_reset_email(*, to: str, name: str | None, token: str) -> None:
    link = f"{settings.app_base_url}/reset?token={token}"
    greeting = f"Hi {name}," if name else "Hi,"
    html = (
        f"<div style='font-family:system-ui,sans-serif;max-width:480px'>"
        f"<h2>Reset your password</h2>"
        f"<p>{greeting}</p>"
        f"<p>We received a request to reset your MetaHarmonizer password. "
        f"Click below to choose a new one.</p>"
        f"<p>{_button(link, 'Reset password')}</p>"
        f"<p style='color:#64748b;font-size:13px'>This link expires in 30 minutes. "
        f"If you didn't request this, you can safely ignore this email — your "
        f"password won't change.</p>"
        f"</div>"
    )
    await _send(
        to,
        "Reset your MetaHarmonizer password",
        html,
    )


async def send_admin_new_signup_email(
    *, to: str, applicant_email: str, applicant_name: str | None
) -> None:
    """Tell an admin a new untrusted-domain account is waiting for approval."""
    link = f"{settings.app_base_url}/admin"
    who = f"{applicant_name} ({applicant_email})" if applicant_name else applicant_email
    html = (
        f"<div style='font-family:system-ui,sans-serif;max-width:480px'>"
        f"<h2>New account awaiting approval</h2>"
        f"<p><strong>{who}</strong> registered with an email outside your trusted "
        f"domains and needs an administrator to approve access.</p>"
        f"<p>{_button(link, 'Review in the admin dashboard')}</p>"
        f"<p style='color:#64748b;font-size:13px'>Approve or reject the account from "
        f"the Admin page.</p>"
        f"</div>"
    )
    await _send(
        to,
        "MetaHarmonizer \u2014 a new account needs approval",
        html,
    )


async def send_account_approved_email(*, to: str, name: str | None) -> None:
    """Tell a user an admin approved their account so they can now sign in."""
    link = f"{settings.app_base_url}/login"
    greeting = f"Hi {name}," if name else "Hi,"
    html = (
        f"<div style='font-family:system-ui,sans-serif;max-width:480px'>"
        f"<h2>Your account is approved</h2>"
        f"<p>{greeting}</p>"
        f"<p>An administrator has approved your MetaHarmonizer account. You can now "
        f"sign in and start harmonizing.</p>"
        f"<p>{_button(link, 'Sign in')}</p>"
        f"</div>"
    )
    await _send(
        to,
        "Your MetaHarmonizer account is approved",
        html,
    )


async def send_account_rejected_email(*, to: str, name: str | None) -> None:
    """Tell a user an admin declined their access request."""
    greeting = f"Hi {name}," if name else "Hi,"
    html = (
        f"<div style='font-family:system-ui,sans-serif;max-width:480px'>"
        f"<h2>Account request declined</h2>"
        f"<p>{greeting}</p>"
        f"<p>Thanks for your interest in MetaHarmonizer. An administrator was unable "
        f"to approve your account at this time. If you believe this is a mistake, "
        f"please reach out to your MetaHarmonizer administrator.</p>"
        f"</div>"
    )
    await _send(
        to,
        "About your MetaHarmonizer account",
        html,
    )
