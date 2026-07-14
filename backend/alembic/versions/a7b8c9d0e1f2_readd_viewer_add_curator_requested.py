"""re-add viewer role + add curator_requested

Re-introduces the ``viewer`` role (default for new signups) and adds
``users.curator_requested`` so a viewer can request curator access for an
admin to approve — mirroring the existing ``admin_requested`` flow.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Viewer's request-to-become-curator flag (mirrors admin_requested).
    op.add_column(
        "users",
        sa.Column(
            "curator_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # Re-introduce the viewer role. Existing accounts keep their roles; new
    # signups default to viewer (enforced in the app layer).
    op.drop_constraint(op.f("ck_users_role_valid"), "users", type_="check")
    op.create_check_constraint(
        op.f("ck_users_role_valid"), "users", "role in ('viewer','curator','admin')"
    )


def downgrade() -> None:
    # Collapse viewers back to curators before tightening the constraint.
    op.execute("UPDATE users SET role = 'curator' WHERE role = 'viewer'")
    op.drop_constraint(op.f("ck_users_role_valid"), "users", type_="check")
    op.create_check_constraint(
        op.f("ck_users_role_valid"), "users", "role in ('curator','admin')"
    )
    op.drop_column("users", "curator_requested")
