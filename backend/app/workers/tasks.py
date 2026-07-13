"""
Harmonize job task (Sprint 4).

The single source of truth for *running* a harmonization, shared by both the
arq worker (``queue`` mode) and the inline executor (``inline`` mode). It:

- drives the job_runs lifecycle (queued -> running -> succeeded/failed/cancelled),
- publishes stage-by-stage progress on the Redis bus (so every connected user
  sees live updates regardless of which process runs the work),
- checks the cancel flag at each stage boundary,
- runs the CPU-heavy engine pipeline in a worker thread so the API event loop
  stays responsive for other concurrent users.
"""

from __future__ import annotations

import functools
import logging

import anyio
import pandas as pd

from app.core.jobs import (
    JobCancelled,
    clear_cancel,
    is_cancelled,
    notify_user,
    publish_progress,
)
from app.core.storage import get_storage
from app.db.session import SessionLocal
from app.engine_adapter import get_engine
from app.repositories import audit as audit_repo
from app.repositories import jobs as jobs_repo
from app.repositories import mappings as mappings_repo
from app.repositories import ontology as ontology_repo
from app.repositories import studies as studies_repo

logger = logging.getLogger("app.jobs")

# Stage weights for a smooth progress bar (parse, schema, ontology, finalize).
_STAGES = [
    ("parse", "Reading file", 10),
    ("schema", "Mapping columns to schema", 55),
    ("ontology", "Resolving ontology terms", 90),
    ("done", "Finalizing", 100),
]


async def _emit(study_id: str, *, stage: str, message: str, pct: int, state: str = "running") -> None:
    await publish_progress(
        study_id,
        {"type": "progress", "stage": stage, "message": message, "pct": pct, "state": state},
    )


async def _checkpoint(study_id: str) -> None:
    """Raise if a cancel was requested — called at every stage boundary."""
    if await is_cancelled(study_id):
        raise JobCancelled()


async def _set_status(study_id: str, status: str) -> None:
    """Persist a study status change in its own short-lived transaction."""
    async with SessionLocal() as session:
        await studies_repo.update_status(session, study_id, status)
        await session.commit()


def _run_pipeline(
    study_id: str,
    file_path: str,
    suffix: str,
    curated_path: str,
    *,
    mode: str = "both",
    ontology_columns: list[str] | None = None,
) -> dict:
    """Synchronous, CPU-heavy engine work — executed in a worker thread.

    ``mode`` selects which mappers run:

    - ``"both"``      : schema mapping then value→ontology mapping (default).
    - ``"schema"``    : SchemaMapper only — column→field, no ontology pass.
    - ``"ontology"``  : OntologyMapper only — return just the value→ontology
                        results. Schema mapping is still run *internally* to
                        resolve each column's curated field, because the
                        ontology vocabularies are keyed by curated field (e.g.
                        ``sex``, ``body_site``) — not by the raw column name.
                        Without that resolution a column like ``gender`` would
                        never route to the ``sex`` value dictionary, so the
                        ontology output would silently differ from ``both``.
                        The internal schema mappings are not persisted.

    ``ontology_columns`` scopes the ontology pass (in both ``"both"`` and
    ``"ontology"`` modes): when provided, only those columns are value-mapped.
    Leave it empty to resolve every column.

    Returns the raw engine results; persistence happens back on the event loop
    via async repositories (a worker thread can't use the async session)."""
    sep = "\t" if suffix in (".tsv", ".txt") else ","
    with get_storage().local(file_path) as local_csv:
        raw_df = pd.read_csv(local_csv, sep=sep, low_memory=False)

        engine = get_engine()
        scope = {c.strip() for c in (ontology_columns or []) if c and c.strip()}

        schema_results: list[dict] = []
        onto_results: list[dict] = []

        # Schema mapping is needed for every mode except a pure ontology run with
        # no work — even "ontology" needs it to resolve each column's curated
        # field so the value pass routes to the right vocabulary.
        schema_all: list[dict] = []
        if mode in ("both", "schema", "ontology"):
            curated_df = pd.read_csv(curated_path, low_memory=False)
            schema_all = engine.harmonize_schema(raw_df, curated_df, csv_path=str(local_csv))

        # Only "both" and "schema" expose the schema mappings to the curator.
        if mode in ("both", "schema"):
            schema_results = schema_all

        if mode in ("both", "ontology"):
            schema_for_onto = schema_all
            if scope:
                schema_for_onto = [
                    m for m in schema_all if m.get("raw_column") in scope
                ]
            onto_results = engine.map_values(raw_df, schema_for_onto) or []

        return {
            "schema_results": schema_results,
            "onto_results": onto_results,
            "mode": mode,
            "columns": len(schema_results),
            "rows": int(len(raw_df)),
            "ontology_values": len(onto_results),
        }


async def run_harmonize(
    *,
    job_id: int,
    study_id: str,
    file_path: str,
    suffix: str,
    curated_path: str,
    owner_id: int | None = None,
    mode: str = "both",
    ontology_columns: list[str] | None = None,
) -> None:
    """Execute one harmonize job end-to-end. Never raises — terminal state is
    recorded in job_runs and broadcast on the bus."""
    async with SessionLocal() as session:
        job = await jobs_repo.get_job(session, job_id)
        if job is None:
            logger.warning("run_harmonize: job %s not found", job_id)
            return
        await jobs_repo.mark_running(session, job)
        await session.commit()

    try:
        await _checkpoint(study_id)
        await _emit(study_id, stage="parse", message="Reading file", pct=10)

        await _set_status(study_id, "processing")
        _schema_msg = (
            "Resolving ontology terms"
            if mode == "ontology"
            else "Mapping columns to schema"
        )
        await _emit(study_id, stage="schema", message=_schema_msg, pct=30)

        # Heavy engine work off the event loop; re-check cancel before & after.
        await _checkpoint(study_id)
        result = await anyio.to_thread.run_sync(
            functools.partial(
                _run_pipeline,
                study_id,
                file_path,
                suffix,
                curated_path,
                mode=mode,
                ontology_columns=ontology_columns,
            )
        )
        await _checkpoint(study_id)

        # Persist engine output on the event loop via async repositories.
        schema_results = result.pop("schema_results")
        onto_results = result.pop("onto_results")
        async with SessionLocal() as session:
            await mappings_repo.insert_mappings(session, study_id, schema_results)
            if onto_results:
                await ontology_repo.insert_ontology_mappings(
                    session, study_id, onto_results
                )
            # Pre-apply the curator's remembered decisions (ADR-0002 read path).
            await session.flush()
            from app.services.learned_apply import apply_learned_decisions

            n_kb = await apply_learned_decisions(session, study_id, owner_id)
            await session.commit()
        if n_kb:
            logger.info("kb: pre-applied %d learned decision(s) for study %s",
                        n_kb, study_id)

        # Record the engine bundle that produced this study (reproducibility /
        # G4): engine version + loaded models go to the append-only audit log so
        # "what produced this mapping?" is always answerable. Best-effort:
        # provenance must never fail an otherwise-good harmonize.
        try:
            health = get_engine().health()
            async with SessionLocal() as session:
                await audit_repo.add_audit_entry(
                    session,
                    study_id=study_id,
                    action="harmonize.completed",
                    actor_id=owner_id,
                    new_value=f"{health.name} {health.version}",
                    details={
                        "engine": health.name,
                        "engine_version": health.version,
                        "models": health.loaded_models,
                        "mode": mode,
                    },
                )
                await session.commit()
        except Exception:  # noqa: BLE001 — provenance is best-effort
            logger.warning(
                "engine-bundle provenance not recorded for study %s", study_id, exc_info=True
            )

        await _emit(study_id, stage="ontology", message="Resolving ontology terms", pct=90)
        await _set_status(study_id, "review")

        async with SessionLocal() as session:
            job = await jobs_repo.get_job(session, job_id)
            if job:
                await jobs_repo.mark_succeeded(session, job)
                await session.commit()

        await clear_cancel(study_id)
        await publish_progress(
            study_id,
            {
                "type": "complete",
                "stage": "done",
                "state": "succeeded",
                "pct": 100,
                "message": f"Harmonization complete — {result['columns']} columns.",
                "result": result,
            },
        )
        if owner_id:
            await notify_user(
                owner_id,
                {"type": "job_complete", "study_id": study_id, "result": result},
            )

    except JobCancelled:
        await _set_status(study_id, "cancelled")
        async with SessionLocal() as session:
            job = await jobs_repo.get_job(session, job_id)
            if job:
                await jobs_repo.mark_cancelled(session, job)
                await session.commit()
        await clear_cancel(study_id)
        await publish_progress(
            study_id,
            {"type": "cancelled", "stage": "done", "state": "cancelled", "pct": 0,
             "message": "Harmonization cancelled."},
        )

    except Exception as exc:  # noqa: BLE001 — terminal failure is recorded, not raised
        logger.exception("harmonize job %s failed", job_id)
        await _set_status(study_id, "failed")
        async with SessionLocal() as session:
            job = await jobs_repo.get_job(session, job_id)
            if job:
                exhausted = job.attempt >= _max_attempts()
                await jobs_repo.mark_failed(
                    session,
                    job,
                    error_code="ENGINE_ERROR",
                    error_message=str(exc),
                    dead_letter=exhausted,
                )
                await session.commit()
        await publish_progress(
            study_id,
            {"type": "failed", "stage": "done", "state": "failed", "pct": 0,
             "message": "Harmonization failed. Please try again."},
        )


def _max_attempts() -> int:
    from app.core.settings import settings

    return settings.job_max_attempts


async def nightly_labeled_export() -> dict:
    """Write the global labeled dataset (G9/U16) to ``backend/data/exports/labeled/``.

    Dumps every study's curator-confirmed schema + ontology mappings as a dated
    CSV and JSONL plus a stable ``labeled-latest.*`` pointer, so a consumer can
    pull the confirmed-mapping corpus without recomputing. Runs nightly via the
    arq cron; safe to invoke manually. Never raises — a failure is logged."""
    import datetime as _dt
    from pathlib import Path

    from app.services.exporter import export_all_labeled

    out_dir = Path(__file__).resolve().parents[2] / "data" / "exports" / "labeled"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.date.today().isoformat()
    written: dict[str, str] = {}
    try:
        async with SessionLocal() as session:
            for ext in ("csv", "jsonl"):
                content = await export_all_labeled(session, ext)
                (out_dir / f"labeled-{stamp}.{ext}").write_text(content, encoding="utf-8")
                (out_dir / f"labeled-latest.{ext}").write_text(content, encoding="utf-8")
                written[ext] = str(out_dir / f"labeled-{stamp}.{ext}")
        logger.info("nightly_labeled_export wrote %s", written)
    except Exception:  # noqa: BLE001 — a scheduled job must not crash the worker
        logger.exception("nightly_labeled_export failed")
    return written
