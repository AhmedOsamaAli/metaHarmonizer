"""
Transactional email (verification + password reset) via Resend.

Sending is best-effort and isolated here so routers don't touch HTTP/email
details. When ``RESEND_API_KEY`` is set, mail goes out through Resend's REST
API. When it's unset, we fall back to logging the link — convenient for local
development, and never used in production (set the key there).
"""

from __future__ import annotations

import logging
from html import escape

import httpx

from app.core.settings import settings

logger = logging.getLogger("app.email")

RESEND_ENDPOINT = "https://api.resend.com/emails"


async def _send(to: str, subject: str, html: str, *, text_fallback: str) -> None:
    """Send one email via Resend, or log it when no API key is configured."""
    if not settings.resend_api_key:
        # No key: log the link so the flow stays testable in local dev.
        logger.warning("email (no RESEND_API_KEY) -> %s | %s\n%s", to, subject, text_fallback)
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
        logger.exception("Resend delivery failed for %s", to)


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
        text_fallback=f"Verify your email: {link}",
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
        text_fallback=f"Reset your password: {link}",
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
        text_fallback=f"{who} needs approval: {link}",
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
        text_fallback=f"Your account is approved. Sign in: {link}",
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
        text_fallback="Your MetaHarmonizer account request was declined.",
    )


async def send_support_ticket_confirmation(
    *, to: str, name: str | None, ticket_id: int, subject: str
) -> None:
    link = f"{settings.app_base_url}/support"
    greeting = f"Hi {escape(name)}," if name else "Hi,"
    html = (
        "<div style='font-family:system-ui,sans-serif;max-width:520px'>"
        f"<h2>Support request #{ticket_id} received</h2><p>{greeting}</p>"
        f"<p>We received your request: <strong>{escape(subject)}</strong>.</p>"
        "<p>The support team will follow up in the application and by email.</p>"
        f"<p>{_button(link, 'View support requests')}</p></div>"
    )
    await _send(
        to,
        f"MetaHarmonizer support request #{ticket_id}",
        html,
        text_fallback=f"Support request #{ticket_id} received: {link}",
    )


async def send_admin_support_ticket_email(
    *, to: str, ticket_id: int, requester: str, category: str, subject: str
) -> None:
    link = f"{settings.app_base_url}/support?ticket={ticket_id}"
    html = (
        "<div style='font-family:system-ui,sans-serif;max-width:520px'>"
        f"<h2>New support request #{ticket_id}</h2>"
        f"<p><strong>From:</strong> {escape(requester)}<br>"
        f"<strong>Category:</strong> {escape(category)}<br>"
        f"<strong>Subject:</strong> {escape(subject)}</p>"
        f"<p>{_button(link, 'Review support request')}</p></div>"
    )
    await _send(
        to,
        f"MetaHarmonizer support #{ticket_id}: {subject}",
        html,
        text_fallback=f"New support request #{ticket_id} from {requester}: {link}",
    )


async def send_support_update_email(
    *, to: str, name: str | None, ticket_id: int, subject: str, update: str
) -> None:
    link = f"{settings.app_base_url}/support?ticket={ticket_id}"
    greeting = f"Hi {escape(name)}," if name else "Hi,"
    html = (
        "<div style='font-family:system-ui,sans-serif;max-width:520px'>"
        f"<h2>Support request #{ticket_id} updated</h2><p>{greeting}</p>"
        f"<p><strong>{escape(subject)}</strong></p><p>{escape(update)}</p>"
        f"<p>{_button(link, 'View update')}</p></div>"
    )
    await _send(
        to,
        f"Update on MetaHarmonizer support #{ticket_id}",
        html,
        text_fallback=f"Support request #{ticket_id} updated: {link}",
    )
