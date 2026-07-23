"""add performance indexes for hot read paths

Evidence-based indexes for queries that scale with data volume:
- studies listed per owner, newest first (dashboard): (owner_id, created_at).
- active sessions looked up per user: (user_id).
- audit log ordered/ranged by created_at + nightly retention purge: (created_at).

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-07-23
"""

from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, None] = "e2f3a4b5c6d7"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_index("ix_studies_owner_created", "studies", ["owner_id", "created_at"])
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_index("ix_studies_owner_created", table_name="studies")
