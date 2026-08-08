"""add learned decision promotion dismissals

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-08-08
"""

from alembic import op
import sqlalchemy as sa


revision = "c6d7e8f9a0b1"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learned_decision_dismissals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_key", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("source_key", sa.Text(), nullable=False),
        sa.Column("decision", sa.String(length=10), nullable=False),
        sa.Column("target_field", sa.Text(), nullable=True),
        sa.Column("target_term", sa.Text(), nullable=True),
        sa.Column("target_id", sa.String(length=100), nullable=True),
        sa.Column("dismissed_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind in ('schema','ontology')", name="learned_dismissal_kind_valid"),
        sa.CheckConstraint("decision in ('accept','reject')", name="learned_dismissal_decision_valid"),
        sa.ForeignKeyConstraint(["dismissed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_key"),
    )
    op.create_index(
        "ix_learned_dismissals_source",
        "learned_decision_dismissals",
        ["kind", "source_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_learned_dismissals_source", table_name="learned_decision_dismissals")
    op.drop_table("learned_decision_dismissals")