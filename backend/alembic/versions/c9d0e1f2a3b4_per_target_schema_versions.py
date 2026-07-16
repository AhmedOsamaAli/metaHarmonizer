"""per-target schema versions

Give each engine target schema (gdc / cbioportal / cmd / …) its own version
lineage: add ``schema_versions.target_schema``, make the version label unique
*within* a target (not globally), and enforce at most one current version per
target with a partial unique index. Existing rows are backfilled to the
``cbioportal`` target via the column's server default.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Which engine target schema a version belongs to. server_default backfills
    # existing rows to cbioportal (the historical single lineage).
    op.add_column(
        "schema_versions",
        sa.Column(
            "target_schema",
            sa.String(length=100),
            nullable=False,
            server_default="cbioportal",
        ),
    )
    # Label is now unique *within* a target, not globally.
    op.drop_constraint("uq_schema_versions_label", "schema_versions", type_="unique")
    op.create_unique_constraint(
        "uq_schema_versions_target_label",
        "schema_versions",
        ["target_schema", "label"],
    )
    # At most one current version per target (partial unique index).
    op.create_index(
        "uq_schema_versions_current_per_target",
        "schema_versions",
        ["target_schema"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_schema_versions_current_per_target", table_name="schema_versions"
    )
    op.drop_constraint(
        "uq_schema_versions_target_label", "schema_versions", type_="unique"
    )
    op.create_unique_constraint(
        "uq_schema_versions_label", "schema_versions", ["label"]
    )
    op.drop_column("schema_versions", "target_schema")
