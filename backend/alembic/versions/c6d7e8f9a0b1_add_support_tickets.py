"""add support tickets and replies

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-08-05
"""

from alembic import op
import sqlalchemy as sa


revision = "c6d7e8f9a0b1"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
        sa.Column("screenshot_key", sa.Text(), nullable=True),
        sa.Column("screenshot_name", sa.String(length=255), nullable=True),
        sa.Column("screenshot_type", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("category in ('question','bug','data','feature','other')", name="support_ticket_category_valid"),
        sa.CheckConstraint("status in ('open','in_progress','resolved')", name="support_ticket_status_valid"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_tickets")),
    )
    op.create_index("ix_support_tickets_creator_created", "support_tickets", ["created_by", "created_at"])
    op.create_index("ix_support_tickets_status_created", "support_tickets", ["status", "created_at"])
    op.create_table(
        "support_ticket_replies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ticket_id"], ["support_tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_ticket_replies")),
    )
    op.create_index("ix_support_replies_ticket_created", "support_ticket_replies", ["ticket_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_support_replies_ticket_created", table_name="support_ticket_replies")
    op.drop_table("support_ticket_replies")
    op.drop_index("ix_support_tickets_status_created", table_name="support_tickets")
    op.drop_index("ix_support_tickets_creator_created", table_name="support_tickets")
    op.drop_table("support_tickets")