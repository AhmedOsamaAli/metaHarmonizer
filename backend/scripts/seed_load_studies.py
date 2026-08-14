"""Create one review-ready study per curator in an isolated capacity stack."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import httpx


def main() -> None:
    if os.getenv("CAPACITY_TEST_MODE") != "1":
        raise SystemExit("CAPACITY_TEST_MODE=1 is required")
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://api:8000")
    parser.add_argument("--prefix", default="load-user")
    parser.add_argument("--domain", default="capacity.metaharmonizer.online")
    parser.add_argument("--password", default=os.getenv("LOAD_TEST_PASSWORD"))
    parser.add_argument("--fixture", type=Path, default=Path("/metadata_samples/new_meta.csv"))
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()
    if not args.password:
        parser.error("set LOAD_TEST_PASSWORD or pass --password")
    if not args.fixture.is_file():
        parser.error(f"fixture not found: {args.fixture}")
    if not 1 <= args.count <= 200:
        parser.error("count must be between 1 and 200")

    pending: dict[str, tuple[str, str]] = {}
    with httpx.Client(base_url=args.base_url, timeout=60) as client:
        for index in range(1, args.count + 1):
            email = f"{args.prefix}-{index:03d}@{args.domain}"
            login = client.post("/api/v1/auth/login", json={"email": email, "password": args.password})
            login.raise_for_status()
            token = login.json()["access_token"]
            with args.fixture.open("rb") as fixture:
                response = client.post(
                    "/api/v1/harmonize",
                    headers={"Authorization": f"Bearer {token}"},
                    files={"file": (f"load-study-{index:03d}.csv", fixture, "text/csv")},
                    data={"mode": "schema"},
                )
            response.raise_for_status()
            pending[response.json()["study_id"]] = (token, email)

        deadline = time.monotonic() + args.timeout_seconds
        while pending and time.monotonic() < deadline:
            for study_id, (token, email) in list(pending.items()):
                response = client.get(
                    f"/api/v1/studies/{study_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                response.raise_for_status()
                status = response.json()["status"]
                if status == "review":
                    pending.pop(study_id)
                elif status in {"failed", "cancelled"}:
                    raise RuntimeError(f"load study for {email} entered {status}")
            if pending:
                time.sleep(2)

    if pending:
        raise TimeoutError(f"{len(pending)} load studies did not become review-ready")
    print(f"created {args.count} isolated review-ready studies")


if __name__ == "__main__":
    main()