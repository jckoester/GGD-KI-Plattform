"""Mehrmodell-Bildgenerierung: assistants.image_kinds

Die Bildarten (IDs aus config/image_models.yaml), die dieser Assistent führen darf.

**Leer = alle konfigurierten.** Das ist der Grund, warum es keine Datenmigration gibt:
Bestandsassistenten behalten mit dem Default `[]` exakt ihr bisheriges Verhalten, und ein
Rollback ist folgenlos.

Revision ID: 0047
Revises: 0046
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade():
    # JSONB wie `tool_groups` (nicht ARRAY(Text) wie `disabled_augmentations`): Beides sind
    # Listen kurzer Schlüssel, aber die Bildarten wandern als JSON-Liste durch die API,
    # und die Nachbarspalte macht es genauso.
    op.add_column(
        "assistants",
        sa.Column(
            "image_kinds",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade():
    op.drop_column("assistants", "image_kinds")
