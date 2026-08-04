"""add version-scoped shared engine proposal cache

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-08-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "engine_proposals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scope_key", sa.String(length=240), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("source_key", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("engine_version", sa.String(length=100), nullable=True),
        sa.Column("use_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind in ('schema','ontology')", name="engine_proposal_kind_valid"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_engine_proposals")),
        sa.UniqueConstraint("scope_key", "kind", "source_key", name="uq_engine_proposal_scope_key"),
    )
    op.create_index(
        "ix_engine_proposals_lookup", "engine_proposals",
        ["scope_key", "kind", "source_key"], unique=False,
    )
    op.create_index(
        "ix_engine_proposals_last_used", "engine_proposals", ["last_used_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_engine_proposals_last_used", table_name="engine_proposals")
    op.drop_index("ix_engine_proposals_lookup", table_name="engine_proposals")
    op.drop_table("engine_proposals")