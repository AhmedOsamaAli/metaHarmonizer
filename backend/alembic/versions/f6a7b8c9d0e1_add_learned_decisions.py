"""add learned_decisions (two-layer curation KB, ADR-0002)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-07

Remembered curator decisions reused across studies: a per-curator ``personal``
layer and an admin-promoted ``shared`` layer. Partial unique indexes scope
uniqueness per layer (a plain composite UNIQUE would let NULL owner_id on shared
rows collide silently).
"""

from alembic import op
import sqlalchemy as sa


revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learned_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=10), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("source_key", sa.Text(), nullable=False),
        sa.Column("decision", sa.String(length=10), nullable=False),
        sa.Column("target_field", sa.Text(), nullable=True),
        sa.Column("target_term", sa.Text(), nullable=True),
        sa.Column("target_id", sa.String(length=100), nullable=True),
        sa.Column("origin_study_id", sa.String(length=64), nullable=True),
        sa.Column("support_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("promoted_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"],
                                name=op.f("fk_learned_decisions_owner_id_users"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["promoted_by"], ["users.id"],
                                name=op.f("fk_learned_decisions_promoted_by_users"),
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learned_decisions")),
        sa.CheckConstraint("scope in ('personal','shared')", name="learned_scope_valid"),
        sa.CheckConstraint("kind in ('schema','ontology')", name="learned_kind_valid"),
        sa.CheckConstraint("decision in ('accept','reject')", name="learned_decision_valid"),
    )
    op.create_index("ix_learned_decisions_lookup", "learned_decisions",
                    ["kind", "source_key"])
    op.create_index("uq_learned_personal", "learned_decisions",
                    ["owner_id", "kind", "source_key"], unique=True,
                    postgresql_where=sa.text("scope = 'personal'"))
    op.create_index("uq_learned_shared", "learned_decisions",
                    ["kind", "source_key"], unique=True,
                    postgresql_where=sa.text("scope = 'shared'"))


def downgrade() -> None:
    op.drop_index("uq_learned_shared", table_name="learned_decisions")
    op.drop_index("uq_learned_personal", table_name="learned_decisions")
    op.drop_index("ix_learned_decisions_lookup", table_name="learned_decisions")
    op.drop_table("learned_decisions")
