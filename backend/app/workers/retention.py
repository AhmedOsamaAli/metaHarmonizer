"""
Data-retention cron job (spec §6.8).

Runs nightly (arq cron in ``arq_worker.py``) and via CLI. Purges aged data so a
long-lived instance's storage/DB stay bounded:
  - uploaded source files older than RETENTION_UPLOADS_DAYS (default 90)
  - generated exports older than RETENTION_EXPORTS_DAYS (default 30)
  - revoked sessions older than RETENTION_REVOKED_SESSIONS_DAYS (default 90)
  - idle (never-completed) studies older than RETENTION_IDLE_STUDY_DAYS
    (default 7) — rows, cascade children, AND their uploaded files
  - audit/activity events older than RETENTION_AUDIT_DAYS (default 365;
    0 = keep forever)

Idempotent and safe: no-ops on empty dirs / no matching rows. Completed studies
and (by default) recent audit history are never touched.

    python -m app.workers.retention            # run once
    python -m app.workers.retention --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete

from app.core.settings import settings
from app.db.models import AuditEvent, EngineProposal
from app.db.models import Session as SessionModel
from app.db.session import SessionLocal
from app.repositories import studies as studies_repo

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
EXPORTS_DIR = DATA_DIR / "exports"


def _purge_dir(directory: Path, older_than_days: int, *, dry_run: bool) -> int:
    """Delete files in ``directory`` older than the cutoff. Returns count."""
    if not directory.exists():
        return 0
    cutoff = time.time() - older_than_days * 86400
    purged = 0
    for path in directory.iterdir():
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.stat().st_mtime < cutoff:
            purged += 1
            if not dry_run:
                path.unlink(missing_ok=True)
    return purged


async def _purge_revoked_sessions(older_than_days: int, *, dry_run: bool) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    async with SessionLocal() as db:
        stmt = delete(SessionModel).where(
            SessionModel.revoked_at.is_not(None),
            SessionModel.revoked_at < cutoff,
        )
        result = await db.execute(stmt)
        if dry_run:
            await db.rollback()
        else:
            await db.commit()
        return result.rowcount or 0


async def _purge_idle_studies(*, dry_run: bool) -> int:
    async with SessionLocal() as db:
        n = await studies_repo.purge_idle_studies_global(db, dry_run=dry_run)
        if dry_run:
            await db.rollback()
        else:
            await db.commit()
        return n


async def _purge_audit(older_than_days: int, *, dry_run: bool) -> int:
    if older_than_days <= 0:
        return 0  # 0 = keep the audit/activity log forever
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    async with SessionLocal() as db:
        result = await db.execute(delete(AuditEvent).where(AuditEvent.created_at < cutoff))
        if dry_run:
            await db.rollback()
        else:
            await db.commit()
        return result.rowcount or 0


async def _purge_engine_proposals(older_than_days: int, *, dry_run: bool) -> int:
    if older_than_days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    async with SessionLocal() as db:
        result = await db.execute(
            delete(EngineProposal).where(EngineProposal.last_used_at < cutoff)
        )
        if dry_run:
            await db.rollback()
        else:
            await db.commit()
        return result.rowcount or 0


async def run_retention(*, dry_run: bool = False) -> dict[str, int]:
    """Run all retention purges; returns a per-category count."""
    uploads = _purge_dir(UPLOADS_DIR, settings.retention_uploads_days, dry_run=dry_run)
    exports = _purge_dir(EXPORTS_DIR, settings.retention_exports_days, dry_run=dry_run)
    sessions = await _purge_revoked_sessions(
        settings.retention_revoked_sessions_days, dry_run=dry_run
    )
    idle_studies = await _purge_idle_studies(dry_run=dry_run)
    audit = await _purge_audit(settings.retention_audit_days, dry_run=dry_run)
    engine_proposals = await _purge_engine_proposals(
        settings.retention_engine_proposals_days, dry_run=dry_run
    )
    return {
        "uploads": uploads,
        "exports": exports,
        "revoked_sessions": sessions,
        "idle_studies": idle_studies,
        "audit": audit,
        "engine_proposals": engine_proposals,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    counts = asyncio.run(run_retention(dry_run=args.dry_run))
    verb = "would purge" if args.dry_run else "purged"
    print(f"{verb}: " + ", ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
