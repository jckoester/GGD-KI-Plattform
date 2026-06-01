"""KS-Phase-4b: subject_id, min_grade, max_grade an context_nodes

Revision ID: 0021
Revises: 0020
"""

from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "context_nodes",
        sa.Column(
            "subject_id",
            sa.Integer(),
            sa.ForeignKey("subjects.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "context_nodes",
        sa.Column("min_grade", sa.Integer(), nullable=True),
    )
    op.add_column(
        "context_nodes",
        sa.Column("max_grade", sa.Integer(), nullable=True),
    )
    op.create_index(
        "idx_context_nodes_subject_id",
        "context_nodes",
        ["subject_id"],
        postgresql_where=sa.text("subject_id IS NOT NULL"),
    )
    op.create_index(
        "idx_context_nodes_grade",
        "context_nodes",
        ["min_grade", "max_grade"],
        postgresql_where=sa.text("min_grade IS NOT NULL"),
    )


def downgrade():
    op.drop_index("idx_context_nodes_grade", table_name="context_nodes")
    op.drop_index("idx_context_nodes_subject_id", table_name="context_nodes")
    op.drop_column("context_nodes", "max_grade")
    op.drop_column("context_nodes", "min_grade")
    op.drop_column("context_nodes", "subject_id")
