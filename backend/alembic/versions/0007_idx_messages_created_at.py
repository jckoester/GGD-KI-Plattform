"""idx_messages_created_at

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-26
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("idx_messages_created_at", "messages", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_messages_created_at", table_name="messages")
