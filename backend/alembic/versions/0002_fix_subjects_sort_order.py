"""fix subjects.sort_order nullable

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-01 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    # Fix sort_order to be NOT NULL (has default 0)
    op.alter_column("subjects", "sort_order", nullable=False)


def downgrade():
    # Revert to nullable
    op.alter_column("subjects", "sort_order", nullable=True)
