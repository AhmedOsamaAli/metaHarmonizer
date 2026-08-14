"""Seed distinct curator accounts for an isolated capacity-test database."""

from __future__ import annotations

import argparse
import asyncio
import os

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.repositories import users as users_repo


async def seed_users(prefix: str, domain: str, password: str, count: int) -> None:
    password_hash = hash_password(password)
    async with SessionLocal() as db:
        for index in range(1, count + 1):
            email = f"{prefix}-{index:03d}@{domain}"
            if await users_repo.get_by_email(db, email):
                continue
            user = await users_repo.create_user(
                db,
                email=email,
                password_hash=password_hash,
                name=f"Load User {index:03d}",
                role="curator",
                approved=True,
            )
            await users_repo.set_email_verified(db, user)
        await db.commit()
    print(f"seeded {count} isolated load-test users")


def main() -> None:
    if os.getenv("CAPACITY_TEST_MODE") != "1":
        raise SystemExit("CAPACITY_TEST_MODE=1 is required")
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", default="load-user")
    parser.add_argument("--domain", default="capacity.metaharmonizer.online")
    parser.add_argument("--password", default=os.getenv("LOAD_TEST_PASSWORD"))
    parser.add_argument("--count", type=int, default=50)
    args = parser.parse_args()
    if not args.password:
        parser.error("set LOAD_TEST_PASSWORD or pass --password")
    if not 1 <= args.count <= 200:
        parser.error("count must be between 1 and 200")
    asyncio.run(seed_users(args.prefix, args.domain, args.password, args.count))


if __name__ == "__main__":
    main()