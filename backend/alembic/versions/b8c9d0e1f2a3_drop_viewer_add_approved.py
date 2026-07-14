"""drop viewer role + add users.approved

Removes the ``viewer`` role entirely (the guest preview covers read-only
"just looking"): every account is a ``curator`` by default and may request
``admin``. Adds ``users.approved`` — trusted-domain signups (and the bootstrap
admin) are approved automatically, while anyone else stays pending until an
admin approves them before first sign-in. Drops the now-unused
``curator_requested`` flag.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Any existing viewer becomes a curator before the constraint is tightened.
    op.execute("UPDATE users SET role = 'curator' WHERE role = 'viewer'")
    op.drop_constraint(op.f("ck_users_role_valid"), "users", type_="check")
    op.create_check_constraint(
        op.f("ck_users_role_valid"), "users", "role in ('curator','admin')"
    )

    # Approval gate. Existing accounts are already active, so they're approved;
    # future inserts default to pending (the app sets it True for trusted
    # domains + the bootstrap admin).
    op.add_column(
        "users",
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("users", "approved", server_default=sa.false())

    # The viewer→curator request flow is gone; admin requests remain.
    op.drop_column("users", "curator_requested")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "curator_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.drop_column("users", "approved")
    op.drop_constraint(op.f("ck_users_role_valid"), "users", type_="check")
    op.create_check_constraint(
        op.f("ck_users_role_valid"), "users", "role in ('viewer','curator','admin')"
    )
