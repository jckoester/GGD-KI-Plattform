"""context_nodes.title_locked: Admin-Titel-Korrekturen überleben BP-Re-Import (C1)

Der BP-Import überschreibt den Titel bisher bei jedem Lauf aus der Quelle. Setzt eine
Admin den Titel manuell (Quell-Titel enthält gelegentlich Fehler), markiert `title_locked`
den Knoten; der Import lässt den Titel dann unangetastet.

Revision ID: 0037
Revises: 0036
"""

from alembic import op
import sqlalchemy as sa

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "context_nodes",
        sa.Column(
            "title_locked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade():
    op.drop_column("context_nodes", "title_locked")
