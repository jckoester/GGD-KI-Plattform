"""Phase 13: assistants.disabled_augmentations

Pro Assistent deaktivierte Lernverhalten-Augmentierungen (Keys aus pedagogy.yaml).
Greift nur in der Schüler-Behandlung beim System-Prompt-Aufbau.

Revision ID: 0032
Revises: 0031
"""

from alembic import op
import sqlalchemy as sa

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "assistants",
        sa.Column(
            "disabled_augmentations",
            sa.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade():
    op.drop_column("assistants", "disabled_augmentations")
