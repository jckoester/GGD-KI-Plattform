"""fix assistants status and force_cost_display NOT NULL

Revision ID: 0003
Revises: 0002
Create Date: 2024-01-01 00:00:00.000000

"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("assistants", "status", nullable=False)
    op.alter_column("assistants", "force_cost_display", nullable=False)


def downgrade():
    op.alter_column("assistants", "status", nullable=True)
    op.alter_column("assistants", "force_cost_display", nullable=True)
