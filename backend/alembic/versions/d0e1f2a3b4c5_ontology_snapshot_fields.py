"""ontology snapshot identity fields

Add ``engine_version`` and ``source`` to ``ontology_snapshots`` so a snapshot
records *which* engine + KB bundle it represents (the reproducibility half of a
study's two-axis pin). Both nullable — existing rows (there are none in normal
operation) and unpinned local builds are fine without them.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-07-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ontology_snapshots",
        sa.Column("engine_version", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "ontology_snapshots",
        sa.Column("source", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ontology_snapshots", "source")
    op.drop_column("ontology_snapshots", "engine_version")
