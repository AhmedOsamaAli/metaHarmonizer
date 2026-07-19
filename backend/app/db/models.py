"""
ORM models for the persistence foundation (Sprint 2).

Tables here cover studies, mappings (+ versions), ontology mappings, the
append-only audit log, schema/ontology version pins, sessions, API tokens,
job runs, and idempotency keys. Auth-specific columns on ``users`` are filled
in further during Sprint 3.

Import ``app.db.models`` to register every model on ``Base.metadata`` so
Alembic autogenerate sees them.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import OptimisticVersionMixin, TimestampMixin


# Users (auth detail lands in Sprint 3; core columns now)
class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="curator")
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")
    email_verified: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    # Whether the account may sign in and act. Trusted-domain signups (and the
    # bootstrap admin) are approved automatically; anyone else stays pending
    # until an admin approves them.
    approved: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="false"
    )
    # Set when a curator asks to be promoted to admin (at registration or later);
    # an existing admin approves (role -> admin) or rejects (flag cleared).
    admin_requested: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="false"
    )

    __table_args__ = (
        CheckConstraint("role in ('curator','admin')", name="role_valid"),
    )


# Schema / ontology versioning (reproducibility pins)
class SchemaVersion(Base, TimestampMixin):
    __tablename__ = "schema_versions"
    __table_args__ = (
        # A version label is unique within its target schema — each target
        # (gdc / cbioportal / cmd / …) has its own v1, v2, … lineage.
        UniqueConstraint("target_schema", "label", name="uq_schema_versions_target_label"),
        # At most one current version per target schema (partial unique index).
        Index(
            "uq_schema_versions_current_per_target",
            "target_schema",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The engine target schema this version belongs to (gdc / cbioportal / cmd / …).
    target_schema: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default="cbioportal"
    )
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    is_current: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    source_path: Mapped[str | None] = mapped_column(Text)


class OntologySnapshot(Base, TimestampMixin):
    __tablename__ = "ontology_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_current: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    # Identity of the KB/engine that produced this snapshot: the upstream
    # metaharmonizer package version + the offline KB bundle identity (its
    # sha256, or a pin id). Lets a study's ontology mappings be traced to the
    # exact engine + knowledge base — the reproducibility half of the two-axis
    # pin (schema_version_id + ontology_snapshot_id).
    engine_version: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str | None] = mapped_column(Text)


# Studies
class Study(Base, TimestampMixin, OptimisticVersionMixin):
    __tablename__ = "studies"
    __table_args__ = (
        # Idempotency: at most one ACTIVE (pre-review) study per (owner, upload
        # content-hash) — blocks accidental duplicates from a double-click or a
        # network retry, while still allowing the same file to be re-harmonized
        # once the prior run leaves these states.
        Index(
            "uq_studies_active_content",
            "owner_id",
            "content_sha256",
            unique=True,
            postgresql_where=text("status in ('pending','queued','processing')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    file_path: Mapped[str | None] = mapped_column(Text)
    # sha256 of the uploaded file bytes — backs the active-dedup index above.
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    row_count: Mapped[int | None] = mapped_column(Integer)
    column_count: Mapped[int | None] = mapped_column(Integer)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Set when a study is exported. Exporting is the "done" signal: an exported
    # study is cleaned up at the next logout, while in-progress (unexported)
    # work is kept so it can be resumed.
    exported: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    schema_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("schema_versions.id", ondelete="RESTRICT")
    )
    ontology_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("ontology_snapshots.id", ondelete="RESTRICT")
    )

    mappings: Mapped[list["Mapping"]] = relationship(
        back_populates="study", cascade="all, delete-orphan"
    )


# Column-level mappings (+ version history)
class Mapping(Base, TimestampMixin, OptimisticVersionMixin):
    __tablename__ = "mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[str] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), nullable=False
    )
    raw_column: Mapped[str] = mapped_column(Text, nullable=False)
    matched_field: Mapped[str | None] = mapped_column(Text)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    stage: Mapped[str | None] = mapped_column(String(20))
    method: Mapped[str | None] = mapped_column(String(40))
    alternatives: Mapped[list | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    curator_field: Mapped[str | None] = mapped_column(Text)
    curator_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    study: Mapped["Study"] = relationship(back_populates="mappings")

    __table_args__ = (
        Index("ix_mappings_study_id", "study_id"),
        CheckConstraint(
            "status in ('pending','accepted','rejected','new_field')", name="status_valid"
        ),
    )


class MappingVersion(Base):
    """Append-only history of a mapping's states (for rollback + audit)."""

    __tablename__ = "mapping_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mapping_id: Mapped[int] = mapped_column(
        ForeignKey("mappings.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("mapping_id", "version", name="mapping_version_unique"),
    )


# Value-level ontology mappings
class OntologyMapping(Base, TimestampMixin, OptimisticVersionMixin):
    __tablename__ = "ontology_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[str] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(Text, nullable=False)
    raw_value: Mapped[str] = mapped_column(Text, nullable=False)
    ontology_term: Mapped[str | None] = mapped_column(Text)
    ontology_id: Mapped[str | None] = mapped_column(String(100))
    confidence_score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    curator_term: Mapped[str | None] = mapped_column(Text)
    curator_id: Mapped[str | None] = mapped_column(String(100))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (Index("ix_ontology_mappings_study_id", "study_id"),)


# Two-layer curation KB (ADR-0002 — learned curator decisions)
class LearnedDecision(Base, TimestampMixin):
    """Remembered curator decisions reused across studies.

    A ``personal`` row applies only for its owning curator; a ``shared`` row
    (admin-promoted, ``owner_id`` NULL) applies for everyone. When both match,
    the personal row wins for that curator. ``source_key`` is a normalized
    lookup key: the raw column name for ``kind='schema'`` and
    ``'field_name::normalized_raw_value'`` for ``kind='ontology'``.
    """

    __tablename__ = "learned_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String(10), nullable=False)  # personal|shared
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # schema|ontology
    source_key: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)  # accept|reject
    target_field: Mapped[str | None] = mapped_column(Text)
    target_term: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[str | None] = mapped_column(String(100))
    origin_study_id: Mapped[str | None] = mapped_column(String(64))
    support_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    promoted_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    __table_args__ = (
        # Partial unique indexes: NULL owner_id on shared rows would defeat a
        # plain composite UNIQUE (NULLs compare distinct), so scope them.
        Index(
            "uq_learned_personal", "owner_id", "kind", "source_key",
            unique=True, postgresql_where=text("scope = 'personal'"),
        ),
        Index(
            "uq_learned_shared", "kind", "source_key",
            unique=True, postgresql_where=text("scope = 'shared'"),
        ),
        Index("ix_learned_decisions_lookup", "kind", "source_key"),
        CheckConstraint("scope in ('personal','shared')", name="learned_scope_valid"),
        CheckConstraint("kind in ('schema','ontology')", name="learned_kind_valid"),
        CheckConstraint("decision in ('accept','reject')", name="learned_decision_valid"),
    )


# Append-only audit log (G4)
class AuditEvent(Base):
    """Append-only decision log. No UPDATE/DELETE — enforced by a DB trigger
    in the migration (see spec §4.3 / §6.2)."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[str | None] = mapped_column(String(64))
    actor_id: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    mapping_id: Mapped[int | None] = mapped_column(Integer)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_audit_events_study_id", "study_id"),)


# Sessions + API tokens (auth; populated in Sprint 3)
class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    refresh_jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="read")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("scope in ('read','write')", name="scope_valid"),)


# Job runs + idempotency keys (operational contracts)
class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(40))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "state in ('queued','running','succeeded','failed','cancelled')",
            name="state_valid",
        ),
    )


class JobFailure(Base):
    """Dead-letter record for a job that exhausted its retries (spec §6.3).

    Admins can re-queue or discard from here (surface lands in Sprint 4).
    """

    __tablename__ = "job_failures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_runs.id", ondelete="SET NULL")
    )
    study_id: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(40))
    error_message: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_job_failures_study_id", "study_id"),)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer)
    response_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# Federation-lite (G1) — signed cross-instance mapping exchange
class FederationImport(Base):
    """One received export bundle, pending local approval (Q10 two-stage)."""

    __tablename__ = "federation_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_instance: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    signature: Mapped[str | None] = mapped_column(Text)
    signature_valid: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="false"
    )
    mapping_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    imported_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    mappings: Mapped[list["FederationMapping"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "status in ('pending','approved','rejected')", name="fed_import_status_valid"
        ),
    )


class FederationMapping(Base):
    """A single curator-confirmed mapping carried in an imported bundle.

    ``dedup_key`` is unique per source instance so the same mapping arriving in
    two bundles from one peer is not double-counted.
    """

    __tablename__ = "federation_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[int] = mapped_column(
        ForeignKey("federation_imports.id", ondelete="CASCADE"), nullable=False
    )
    source_instance: Mapped[str] = mapped_column(String(120), nullable=False)
    record_type: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_key: Mapped[str] = mapped_column(Text, nullable=False)
    accepted_target: Mapped[str] = mapped_column(Text, nullable=False)
    ontology_id: Mapped[str | None] = mapped_column(String(100))
    confidence_score: Mapped[float | None] = mapped_column(Float)
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    parent: Mapped["FederationImport"] = relationship(back_populates="mappings")

    __table_args__ = (
        UniqueConstraint(
            "source_instance", "dedup_key", name="federation_mapping_source_dedup"
        ),
        Index("ix_federation_mappings_import_id", "import_id"),
        CheckConstraint(
            "record_type in ('schema_mapping','ontology_mapping')",
            name="fed_mapping_type_valid",
        ),
    )

