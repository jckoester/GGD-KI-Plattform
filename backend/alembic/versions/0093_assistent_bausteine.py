"""Assistenten: Bausteine (0.26, Plan „Rückfall-Assistenten“, Schritt 2)

Revision ID: 0093
Revises: 0092
Create Date: 2026-10-28

**`assistants.bausteine`** (JSONB-Liste von Schlüsseln, Vorgabe `[]`): gemessene Textblöcke,
die die Plattform hinter den Prompt hängt (`app/assistants/bausteine/`), etwa
„Begleiten statt lösen“. Leer heißt keiner — bestehende Assistenten ändern sich nicht.

**Rücknahme:** `alembic downgrade 0092` entfernt die Spalte samt Inhalt.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0093"
down_revision = "0092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assistants",
        sa.Column("bausteine", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("assistants", "bausteine")
