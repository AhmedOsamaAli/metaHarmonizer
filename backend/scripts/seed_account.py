"""Seed a pre-registered dashboard account (dev convenience).

Creates one user directly in the database so you can log in without going
through the email-verification flow. If the users table is empty the account
is created as the bootstrap **admin** (auto-verified); otherwise it is a
verified **curator** unless ``--role admin`` is passed.

Usage (from ``backend/`` with the venv active and ``.env`` pointing at the DB)::

    SEED_EMAIL=you@example.com SEED_PASSWORD='S3cret!' python -m scripts.seed_account
    python -m scripts.seed_account --email you@example.com --password "S3cret!" --role admin

Credentials are never printed. Supply the password through ``SEED_PASSWORD`` or
``--password``; prefer the environment variable so it is not exposed in the
process argument list.
"""

from __future__ import annotations

import argparse
import asyncio
import os

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.repositories import users as users_repo


async def seed(email: str, password: str, name: str | None, role: str | None) -> None:
    async with SessionLocal() as db:
        existing = await users_repo.get_by_email(db, email)
        if existing:
            print(f"User already exists: {email} (role={existing.role}). No change.")
            return

        is_bootstrap = await users_repo.count_users(db) == 0
        final_role = role or ("admin" if is_bootstrap else "curator")

        user = await users_repo.create_user(
            db,
            email=email,
            password_hash=hash_password(password),
            name=name or email.split("@")[0],
            role=final_role,
            approved=True,
        )
        await users_repo.set_email_verified(db, user)
        await db.commit()

        print("Account created:")
        print(f"  email    : {email}")
        print(f"  role     : {final_role}")
        print("  verified : yes")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a dashboard account.")
    parser.add_argument("--email", default=os.getenv("SEED_EMAIL"))
    parser.add_argument("--password", default=os.getenv("SEED_PASSWORD"))
    parser.add_argument("--name", default=None)
    parser.add_argument(
        "--role", default=os.getenv("SEED_ROLE"), choices=["admin", "curator"]
    )
    args = parser.parse_args()
    if not args.email:
        parser.error("set SEED_EMAIL or pass --email")
    if not args.password:
        parser.error("set SEED_PASSWORD or pass --password")

    asyncio.run(seed(args.email, args.password, args.name, args.role))


if __name__ == "__main__":
    main()
