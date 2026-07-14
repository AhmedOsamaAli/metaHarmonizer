"""Seed a pre-registered dashboard account (dev convenience).

Creates one user directly in the database so you can log in without going
through the email-verification flow. If the users table is empty the account
is created as the bootstrap **admin** (auto-verified); otherwise it is a
verified **curator** unless ``--role admin`` is passed.

Usage (from ``backend/`` with the venv active and ``.env`` pointing at the DB)::

    python -m scripts.seed_account --email you@example.com
    python -m scripts.seed_account --email you@example.com --password "S3cret!" --role admin

If ``--password`` is omitted a strong random one is generated and printed once.
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import string

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.repositories import users as users_repo


def _random_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


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
        print(f"  password : {password}")
        print(f"  role     : {final_role}")
        print(f"  verified : yes")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a dashboard account.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", default=None)
    parser.add_argument("--name", default=None)
    parser.add_argument("--role", default=None, choices=["admin", "curator"])
    args = parser.parse_args()

    password = args.password or _random_password()
    asyncio.run(seed(args.email, password, args.name, args.role))


if __name__ == "__main__":
    main()
