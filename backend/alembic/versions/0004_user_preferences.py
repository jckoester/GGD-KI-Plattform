"""add user_preferences table

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-20 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            pseudonym    TEXT PRIMARY KEY,
            preferences  JSONB NOT NULL DEFAULT '{}'
        )
    """)


def downgrade() -> None:
    op.drop_table('user_preferences')
