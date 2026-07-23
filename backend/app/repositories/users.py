"""User data access (Sprint 3)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(func.lower(User.email) == email.lower())
    return await db.scalar(stmt)


async def get_by_id(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)


async def count_users(db: AsyncSession) -> int:
    return await db.scalar(select(func.count()).select_from(User)) or 0


async def list_users(db: AsyncSession) -> list[User]:
    stmt = select(User).order_by(User.created_at.asc())
    return list(await db.scalars(stmt))


async def list_admin_emails(db: AsyncSession) -> list[str]:
    """Active admins' emails \u2014 used to notify them of pending approvals."""
    stmt = select(User.email).where(User.role == "admin", User.is_active.is_(True))
    return list(await db.scalars(stmt))


async def create_user(
    db: AsyncSession,
    *,
    email: str,
    password_hash: str | None,
    name: str | None,
    role: str,
    approved: bool = False,
    admin_requested: bool = False,
) -> User:
    user = User(
        email=email,
        password_hash=password_hash,
        name=name,
        role=role,
        approved=approved,
        admin_requested=admin_requested,
    )
    db.add(user)
    await db.flush()
    return user


async def set_email_verified(db: AsyncSession, user: User) -> None:
    """Mark a user's email as confirmed (idempotent)."""
    user.email_verified = True
    await db.flush()


async def set_password(db: AsyncSession, user: User, password_hash: str) -> None:
    """Replace a user's password hash (used by the reset flow)."""
    user.password_hash = password_hash
    await db.flush()
