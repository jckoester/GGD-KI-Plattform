"""add group_id to conversations

Revision ID: 0013
Revises: 0012
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0013'
down_revision: Union[str, None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'conversations',
        sa.Column(
            'group_id',
            sa.Integer(),
            sa.ForeignKey('groups.id', ondelete='SET NULL'),
            nullable=True,
        )
    )
    op.create_index('idx_conversations_group_id', 'conversations', ['group_id'])


def downgrade() -> None:
    op.drop_index('idx_conversations_group_id', table_name='conversations')
    op.drop_column('conversations', 'group_id')
