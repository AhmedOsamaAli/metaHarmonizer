from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import SupportTicket, SupportTicketReply, User


async def create_ticket(
    db: AsyncSession,
    *,
    created_by: int,
    category: str,
    subject: str,
    description: str,
) -> SupportTicket:
    ticket = SupportTicket(
        created_by=created_by,
        category=category,
        subject=subject,
        description=description,
    )
    db.add(ticket)
    await db.flush()
    await db.refresh(ticket)
    return ticket


async def set_screenshot(
    db: AsyncSession,
    ticket: SupportTicket,
    *,
    key: str,
    name: str,
    content_type: str,
) -> None:
    ticket.screenshot_key = key
    ticket.screenshot_name = name
    ticket.screenshot_type = content_type
    await db.flush()


async def list_visible(
    db: AsyncSession, *, user_id: int, is_admin: bool
) -> list[SupportTicket]:
    stmt = select(SupportTicket).order_by(SupportTicket.updated_at.desc())
    if not is_admin:
        stmt = stmt.where(SupportTicket.created_by == user_id)
    return list(await db.scalars(stmt))


async def get_visible(
    db: AsyncSession, ticket_id: int, *, user_id: int, is_admin: bool
) -> SupportTicket | None:
    stmt = select(SupportTicket).where(SupportTicket.id == ticket_id)
    if not is_admin:
        stmt = stmt.where(SupportTicket.created_by == user_id)
    return await db.scalar(stmt)


async def add_reply(
    db: AsyncSession, *, ticket_id: int, author_id: int, body: str
) -> SupportTicketReply:
    reply = SupportTicketReply(ticket_id=ticket_id, author_id=author_id, body=body)
    db.add(reply)
    ticket = await db.get(SupportTicket, ticket_id)
    if ticket is not None:
        ticket.status = "in_progress"
    await db.flush()
    await db.refresh(reply)
    return reply


async def set_status(
    db: AsyncSession, ticket: SupportTicket, status: str
) -> SupportTicket:
    ticket.status = status
    await db.flush()
    await db.refresh(ticket)
    return ticket


async def to_dict(db: AsyncSession, ticket: SupportTicket) -> dict:
    creator = await db.get(User, ticket.created_by)
    rows = (
        await db.execute(
            select(SupportTicketReply, User)
            .join(User, User.id == SupportTicketReply.author_id)
            .where(SupportTicketReply.ticket_id == ticket.id)
            .order_by(SupportTicketReply.created_at.asc())
        )
    ).all()
    return {
        "id": ticket.id,
        "created_by": ticket.created_by,
        "creator_name": creator.name if creator else None,
        "creator_email": creator.email if creator else "deleted-user",
        "creator_role": creator.role if creator else "curator",
        "category": ticket.category,
        "subject": ticket.subject,
        "description": ticket.description,
        "status": ticket.status,
        "screenshot_name": ticket.screenshot_name,
        "has_screenshot": bool(ticket.screenshot_key),
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "replies": [
            {
                "id": reply.id,
                "author_id": reply.author_id,
                "author_name": author.name,
                "author_email": author.email,
                "author_role": author.role,
                "body": reply.body,
                "created_at": reply.created_at,
            }
            for reply, author in rows
        ],
    }
