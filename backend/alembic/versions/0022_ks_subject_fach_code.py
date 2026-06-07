"""KS: fach_code an subjects (Bildungsplan-Fachkürzel)

Revision ID: 0022
Revises: 0021

Hinweis zur Nummerierung: Der Bandmodell-Plan (KS-Bildungsplan-Bandmodell-
Implementierungsplan.md) sieht ebenfalls eine 0022 für die Spalte `niveau`
auf context_nodes vor. Diese Migration belegt 0022 für subjects.fach_code;
die niveau-Migration ist beim Bau auf 0023 (down_revision="0022") zu legen.
"""

from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "subjects",
        sa.Column("fach_code", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_subjects_fach_code",
        "subjects",
        ["fach_code"],
        unique=True,
        postgresql_where=sa.text("fach_code IS NOT NULL"),
    )


def downgrade():
    op.drop_index("idx_subjects_fach_code", table_name="subjects")
    op.drop_column("subjects", "fach_code")
