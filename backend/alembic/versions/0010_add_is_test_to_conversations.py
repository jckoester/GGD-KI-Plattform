"""add is_test to conversations

Revision ID: 0010
Revises: 0009
Create Date: 2025-01-00 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_test column with default false
    op.add_column(
        'conversations',
        sa.Column('is_test', sa.Boolean(), nullable=False, server_default=sa.text('false'))
    )


def downgrade() -> None:
    # Remove is_test column
    op.drop_column('conversations', 'is_test')
