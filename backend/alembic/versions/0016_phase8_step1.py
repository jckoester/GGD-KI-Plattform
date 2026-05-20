"""Phase 8 Schritt 1: messages.assistant_id

Revision ID: 0016
Revises: 0015
"""

from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "messages",
        sa.Column(
            "assistant_id",
            sa.Integer(),
            sa.ForeignKey("assistants.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_messages_assistant_id",
        "messages",
        ["assistant_id"],
    )


def downgrade():
    op.drop_index("idx_messages_assistant_id", "messages")
    op.drop_column("messages", "assistant_id")
