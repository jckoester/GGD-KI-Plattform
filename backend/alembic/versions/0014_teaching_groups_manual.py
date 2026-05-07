"""Phase 5: Teaching groups manual management

Revision ID: 0014_phase5_teaching_groups_manual
Revises: 0013
Create Date: 2025-01-01 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    # Add source_class_group_id column to groups
    op.add_column(
        "groups",
        sa.Column(
            "source_class_group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_groups_source_class_group_id", "groups", ["source_class_group_id"]
    )

    # Create teacher_group_exclusions table
    op.create_table(
        "teacher_group_exclusions",
        sa.Column("pseudonym", sa.Text(), primary_key=True, nullable=False),
        sa.Column(
            "class_group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "subject_id",
            sa.Integer(),
            sa.ForeignKey("subjects.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
    )


def downgrade():
    op.drop_table("teacher_group_exclusions")
    op.drop_index("idx_groups_source_class_group_id", "groups")
    op.drop_column("groups", "source_class_group_id")
