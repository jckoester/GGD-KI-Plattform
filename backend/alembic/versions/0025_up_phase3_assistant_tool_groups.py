"""UP-Phase-3: assistants.tool_groups JSONB

Revision ID: 0025
Revises: 0024
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "assistants",
        sa.Column(
            "tool_groups",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade():
    op.drop_column("assistants", "tool_groups")
