"""KS: Spalte `niveau` an context_nodes (Bandmodell)

Revision ID: 0023
Revises: 0022
"""

from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "context_nodes",
        sa.Column(
            "niveau",
            sa.String(length=16),
            nullable=False,
            server_default="regulär",
        ),
    )
    op.create_index(
        "idx_context_nodes_band",
        "context_nodes",
        ["subject_id", "min_grade", "max_grade", "niveau"],
        postgresql_where=sa.text("subject_id IS NOT NULL"),
    )


def downgrade():
    op.drop_index("idx_context_nodes_band", table_name="context_nodes")
    op.drop_column("context_nodes", "niveau")
