"""Add visibility column to assistants table.

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-28 09:15:54.905072

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: Union[str, Sequence[str], None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('assistants', sa.Column('visibility', sa.Text(), server_default=sa.text("'public'"), nullable=False))
    op.create_check_constraint('check_assistant_visibility', 'assistants', "visibility IN ('public','private','hidden')")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('check_assistant_visibility', 'assistants', type_='check')
    op.drop_column('assistants', 'visibility')
