"""Study data access (Postgres; replaces the legacy SQLite ``database`` module).

Returns plain ``dict`` rows shaped exactly like the old SQLite layer so the
service/router contract is unchanged — notably ``upload_date`` (mapped from
``created_at``) and the ``exported`` purge guard.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.core.storage import get_storage
from app.db.models import Study

# A study the user never completed is treated as abandoned in-progress work and
# is deleted once it's older than this — lazily on the owner's next list load,
# and globally by the nightly retention cron (so abandoned accounts' studies
# don't accumulate). Completed studies are exempt. 0 disables the sweep.
IDLE_STUDY_DAYS = settings.retention_idle_study_days
_ACTIVE_STATUSES = ("pending", "queued", "processing")


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _to_dict(s: Study) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "upload_date": _iso(s.created_at),
        "status": s.status,
        "file_path": s.file_path,
        "row_count": s.row_count,
        "column_count": s.column_count,
        "owner_id": s.owner_id,
        "exported": s.exported,
        "schema_version_id": s.schema_version_id,
        "ontology_snapshot_id": s.ontology_snapshot_id,
    }


async def lock_and_count_active_for_owner(db: AsyncSession, owner_id: int) -> int:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, :owner_id)"),
        {"namespace": 0x4D48, "owner_id": owner_id},
    )
    stmt = select(func.count()).select_from(Study).where(
        Study.owner_id == owner_id,
        Study.status.in_(_ACTIVE_STATUSES),
    )
    return int(await db.scalar(stmt) or 0)


async def create_study(
    db: AsyncSession,
    *,
    study_id: str,
    name: str,
    file_path: str,
    row_count: int,
    column_count: int,
    owner_id: int | None = None,
    schema_version_id: int | None = None,
    ontology_snapshot_id: int | None = None,
    content_sha256: str | None = None,
) -> dict:
    study = Study(
        id=study_id,
        name=name,
        status="pending",
        file_path=file_path,
        row_count=row_count,
        column_count=column_count,
        owner_id=owner_id,
        schema_version_id=schema_version_id,
        ontology_snapshot_id=ontology_snapshot_id,
        content_sha256=content_sha256,
    )
    db.add(study)
    await db.flush()
    await db.refresh(study)
    return _to_dict(study)


async def find_active_by_content(
    db: AsyncSession, *, owner_id: int | None, content_sha256: str | None
) -> dict | None:
    """Return this owner's in-flight study for the same upload content, if any.

    Used to short-circuit accidental double-submits before doing duplicate work.
    Anonymous (NULL owner) uploads are never deduped — SQL treats NULLs as
    distinct, matching the partial unique index.
    """
    if owner_id is None or not content_sha256:
        return None
    stmt = (
        select(Study)
        .where(
            Study.owner_id == owner_id,
            Study.content_sha256 == content_sha256,
            Study.status.in_(_ACTIVE_STATUSES),
        )
        .order_by(Study.created_at.desc())
        .limit(1)
    )
    s = await db.scalar(stmt)
    return _to_dict(s) if s else None


async def get_study(db: AsyncSession, study_id: str) -> dict | None:
    s = await db.get(Study, study_id)
    return _to_dict(s) if s else None


async def list_studies(
    db: AsyncSession,
    owner_id: int | None = None,
    *,
    include_completed: bool = True,
) -> list[dict]:
    """List studies. When ``owner_id`` is given, return only that user's studies
    (per-user visibility); pass ``None`` for the global view.

    ``include_completed`` controls whether finished studies appear: the
    review/ontology/quality/export pickers pass ``False`` (a completed study is
    filed away and shouldn't clutter the work lists); the default keeps them for
    callers that need full history.

    Lazily enforces the idle-expiry policy first: a user's *non-completed*
    studies older than ``IDLE_STUDY_DAYS`` are deleted (completed studies are
    kept). Cleanup runs on the owner's own list load, so no scheduler
    is required for it to take effect."""
    if owner_id is not None:
        await purge_idle_studies(db, owner_id)
    stmt = select(Study).order_by(Study.created_at.desc())
    if owner_id is not None:
        stmt = stmt.where(Study.owner_id == owner_id)
    if not include_completed:
        stmt = stmt.where(Study.status != "completed")
    return [_to_dict(s) for s in await db.scalars(stmt)]


async def mark_exported(db: AsyncSession, study_id: str) -> None:
    """Flag a study as exported. Purely informational (studies persist until the
    user completes them or they idle-expire); kept so exports are recorded."""
    await db.execute(update(Study).where(Study.id == study_id).values(exported=True))


async def update_status(db: AsyncSession, study_id: str, status: str) -> None:
    await db.execute(update(Study).where(Study.id == study_id).values(status=status))


async def mark_completed(db: AsyncSession, study_id: str) -> dict | None:
    """Mark a study ``completed`` — a "filed away, I'm done" signal. The study
    is kept (so its work still counts toward the dashboard) but drops out of the
    work-list pickers and is exempt from idle-expiry."""
    s = await db.get(Study, study_id)
    if not s:
        return None
    s.status = "completed"
    await db.flush()
    return _to_dict(s)


async def delete_study(db: AsyncSession, study_id: str) -> bool:
    """Delete one study (mappings/ontology rows follow via ON DELETE CASCADE).
    Returns True if a row was removed. Ownership is enforced by the caller."""
    res = await db.execute(delete(Study).where(Study.id == study_id))
    return (res.rowcount or 0) > 0


async def _delete_studies(db: AsyncSession, conditions, *, dry_run: bool = False) -> int:
    """Delete studies matching ``conditions`` AND their uploaded source files
    (best-effort). Mapping/ontology rows follow via ON DELETE CASCADE. Returns
    the count; ``dry_run`` counts without deleting."""
    studies = list(await db.scalars(select(Study).where(*conditions)))
    if dry_run or not studies:
        return len(studies)
    storage = get_storage()
    for s in studies:
        if s.file_path:
            try:
                storage.delete(s.file_path)
            except Exception:  # noqa: BLE001 — stray blob is caught by the dir sweep
                pass
    await db.execute(delete(Study).where(Study.id.in_([s.id for s in studies])))
    return len(studies)


async def purge_idle_studies(db: AsyncSession, owner_id: int) -> int:
    """Delete a user's non-completed studies (and their files) older than
    ``IDLE_STUDY_DAYS``. Completed studies are kept (they're done, not
    abandoned)."""
    if IDLE_STUDY_DAYS <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=IDLE_STUDY_DAYS)
    return await _delete_studies(
        db,
        [
            Study.owner_id == owner_id,
            Study.status != "completed",
            Study.created_at < cutoff,
        ],
    )


async def purge_idle_studies_global(db: AsyncSession, *, dry_run: bool = False) -> int:
    """Delete ALL owners' non-completed studies (and their files) older than
    ``IDLE_STUDY_DAYS`` — the nightly sweep so abandoned accounts' studies don't
    accumulate. Completed studies are kept."""
    if IDLE_STUDY_DAYS <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=IDLE_STUDY_DAYS)
    return await _delete_studies(
        db,
        [
            Study.status != "completed",
            Study.created_at < cutoff,
        ],
        dry_run=dry_run,
    )
