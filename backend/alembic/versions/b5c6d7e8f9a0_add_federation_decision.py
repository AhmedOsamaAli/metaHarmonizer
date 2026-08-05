"""add decision to federation mappings

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-08-05
"""

from alembic import op
import sqlalchemy as sa


revision = "b5c6d7e8f9a0"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "federation_mappings",
        sa.Column("decision", sa.String(length=10), server_default="accept", nullable=False),
    )
    op.create_check_constraint(
        "fed_mapping_decision_valid",
        "federation_mappings",
        "decision in ('accept','reject')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fed_mapping_decision_valid", "federation_mappings", type_="check"
    )
    op.drop_column("federation_mappings", "decision")