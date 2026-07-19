"""add studies.content_sha256 + active-dedup partial unique index

Idempotency for POST /harmonize: a per-owner partial unique index blocks a
second ACTIVE (pending/queued/processing) study for the same upload content,
so a double-click or network retry can't spawn duplicate harmonization jobs.
The same file can be re-harmonized once the prior run leaves those states.

Revision ID: e2f3a4b5c6d7
Revises: d0e1f2a3b4c5
Create Date: 2026-07-19
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "studies",
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "uq_studies_active_content",
        "studies",
        ["owner_id", "content_sha256"],
        unique=True,
        postgresql_where=sa.text("status in ('pending','queued','processing')"),
    )


def downgrade() -> None:
    op.drop_index("uq_studies_active_content", table_name="studies")
    op.drop_column("studies", "content_sha256")
