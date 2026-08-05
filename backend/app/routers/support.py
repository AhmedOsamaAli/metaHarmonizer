from __future__ import annotations

import tempfile
import uuid
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import actor_label, current_user, require_scope
from app.core.email import (
    send_admin_support_ticket_email,
    send_support_ticket_confirmation,
    send_support_update_email,
)
from app.core.storage import get_storage
from app.db.models import User
from app.db.session import get_db
from app.repositories import audit as audit_repo
from app.repositories import support_tickets as tickets_repo
from app.repositories import users as users_repo
from app.schemas.support import (
    SupportReplyCreate,
    SupportTicketOut,
    SupportTicketUpdate,
)

router = APIRouter(prefix="/api/v1/support", tags=["support"])

MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024
SCREENSHOT_TYPES = {
    "image/png": (".png", (b"\x89PNG\r\n\x1a\n",)),
    "image/jpeg": (".jpg", (b"\xff\xd8\xff",)),
    "image/webp": (".webp", (b"RIFF",)),
}


def _is_admin(user: User) -> bool:
    return user.role == "admin"


async def _save_screenshot(file: UploadFile, ticket_id: int) -> tuple[str, str, str]:
    content_type = (file.content_type or "").lower()
    if content_type not in SCREENSHOT_TYPES:
        raise HTTPException(400, "Screenshot must be PNG, JPEG, or WebP.")
    suffix, signatures = SCREENSHOT_TYPES[content_type]
    original_name = Path(file.filename or f"screenshot{suffix}").name
    original_name = re.sub(r"[^A-Za-z0-9._-]+", "_", original_name)[:255]
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
            temp_path = Path(temp.name)
            written = 0
            first = b""
            while chunk := await file.read(1024 * 1024):
                if not first:
                    first = chunk[:12]
                written += len(chunk)
                if written > MAX_SCREENSHOT_BYTES:
                    raise HTTPException(413, "Screenshot exceeds the 5 MB limit.")
                temp.write(chunk)
        if written == 0 or not any(first.startswith(signature) for signature in signatures):
            raise HTTPException(400, "Screenshot content does not match its image type.")
        if content_type == "image/webp" and first[8:12] != b"WEBP":
            raise HTTPException(400, "Screenshot content is not a valid WebP image.")
        key = f"support/{ticket_id}/{uuid.uuid4().hex}{suffix}"
        get_storage().store(key, temp_path)
        return key, original_name, content_type
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        await file.close()


async def _out(db: AsyncSession, ticket) -> SupportTicketOut:
    return SupportTicketOut.model_validate(await tickets_repo.to_dict(db, ticket))


@router.post("", response_model=SupportTicketOut, status_code=201)
async def create_support_ticket(
    category: str = Form(...),
    subject: str = Form(..., min_length=3, max_length=200),
    description: str = Form(..., min_length=10, max_length=10000),
    screenshot: UploadFile | None = File(default=None),
    user: User = Depends(require_scope("write")),
    db: AsyncSession = Depends(get_db),
):
    if category not in {"question", "bug", "data", "feature", "other"}:
        raise HTTPException(400, "Invalid support category.")
    ticket = await tickets_repo.create_ticket(
        db,
        created_by=user.id,
        category=category,
        subject=subject.strip(),
        description=description.strip(),
    )
    stored_key: str | None = None
    try:
        if screenshot is not None and screenshot.filename:
            stored_key, name, content_type = await _save_screenshot(screenshot, ticket.id)
            await tickets_repo.set_screenshot(
                db, ticket, key=stored_key, name=name, content_type=content_type
            )
        await audit_repo.add_audit_entry(
            db,
            study_id=None,
            action="support_created",
            actor_id=user.id,
            new_value=f"ticket:{ticket.id}",
            details={"category": category, "has_screenshot": bool(stored_key)},
            curator=actor_label(user),
        )
        await db.commit()
        await db.refresh(ticket)
    except Exception:
        await db.rollback()
        if stored_key:
            get_storage().delete(stored_key)
        raise

    await send_support_ticket_confirmation(
        to=user.email, name=user.name, ticket_id=ticket.id, subject=ticket.subject
    )
    requester = f"{user.name} ({user.email})" if user.name else user.email
    for admin_email in await users_repo.list_admin_emails(db):
        if admin_email.lower() == user.email.lower():
            continue
        await send_admin_support_ticket_email(
            to=admin_email,
            ticket_id=ticket.id,
            requester=requester,
            category=ticket.category,
            subject=ticket.subject,
        )
    return await _out(db, ticket)


@router.get("", response_model=list[SupportTicketOut])
async def list_support_tickets(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    rows = await tickets_repo.list_visible(db, user_id=user.id, is_admin=_is_admin(user))
    return [await _out(db, ticket) for ticket in rows]


@router.get("/{ticket_id}", response_model=SupportTicketOut)
async def get_support_ticket(
    ticket_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ticket = await tickets_repo.get_visible(
        db, ticket_id, user_id=user.id, is_admin=_is_admin(user)
    )
    if ticket is None:
        raise HTTPException(404, "Support ticket not found")
    return await _out(db, ticket)


@router.post("/{ticket_id}/replies", response_model=SupportTicketOut)
async def reply_to_support_ticket(
    ticket_id: int,
    body: SupportReplyCreate,
    user: User = Depends(require_scope("write")),
    db: AsyncSession = Depends(get_db),
):
    ticket = await tickets_repo.get_visible(
        db, ticket_id, user_id=user.id, is_admin=_is_admin(user)
    )
    if ticket is None:
        raise HTTPException(404, "Support ticket not found")
    await tickets_repo.add_reply(
        db, ticket_id=ticket.id, author_id=user.id, body=body.body.strip()
    )
    await audit_repo.add_audit_entry(
        db,
        study_id=None,
        action="support_replied",
        actor_id=user.id,
        new_value=f"ticket:{ticket.id}",
        curator=actor_label(user),
    )
    await db.commit()
    await db.refresh(ticket)
    creator = await users_repo.get_by_id(db, ticket.created_by)
    if _is_admin(user) and creator and creator.id != user.id:
        await send_support_update_email(
            to=creator.email,
            name=creator.name,
            ticket_id=ticket.id,
            subject=ticket.subject,
            update="The support team replied to your request.",
        )
    elif not _is_admin(user):
        requester = f"{user.name} ({user.email})" if user.name else user.email
        for admin_email in await users_repo.list_admin_emails(db):
            await send_admin_support_ticket_email(
                to=admin_email,
                ticket_id=ticket.id,
                requester=requester,
                category=ticket.category,
                subject=f"Reply: {ticket.subject}",
            )
    return await _out(db, ticket)


@router.patch("/{ticket_id}", response_model=SupportTicketOut)
async def update_support_ticket(
    ticket_id: int,
    body: SupportTicketUpdate,
    user: User = Depends(require_scope("write")),
    db: AsyncSession = Depends(get_db),
):
    if not _is_admin(user):
        raise HTTPException(403, "Only administrators can change ticket status.")
    ticket = await tickets_repo.get_visible(db, ticket_id, user_id=user.id, is_admin=True)
    if ticket is None:
        raise HTTPException(404, "Support ticket not found")
    old_status = ticket.status
    await tickets_repo.set_status(db, ticket, body.status)
    await audit_repo.add_audit_entry(
        db,
        study_id=None,
        action="support_status_changed",
        actor_id=user.id,
        old_value=old_status,
        new_value=body.status,
        details={"ticket_id": ticket.id},
        curator=actor_label(user),
    )
    await db.commit()
    await db.refresh(ticket)
    creator = await users_repo.get_by_id(db, ticket.created_by)
    if creator and creator.id != user.id:
        await send_support_update_email(
            to=creator.email,
            name=creator.name,
            ticket_id=ticket.id,
            subject=ticket.subject,
            update=f"Your support request is now {body.status.replace('_', ' ')}.",
        )
    return await _out(db, ticket)


@router.get("/{ticket_id}/screenshot")
async def download_support_screenshot(
    ticket_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ticket = await tickets_repo.get_visible(
        db, ticket_id, user_id=user.id, is_admin=_is_admin(user)
    )
    if ticket is None or not ticket.screenshot_key:
        raise HTTPException(404, "Screenshot not found")
    storage = get_storage()
    if not storage.exists(ticket.screenshot_key):
        raise HTTPException(404, "Screenshot not found")
    with storage.local(ticket.screenshot_key) as path:
        content = path.read_bytes()
    return Response(
        content=content,
        media_type=ticket.screenshot_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{ticket.screenshot_name or "screenshot"}"'
        },
    )
