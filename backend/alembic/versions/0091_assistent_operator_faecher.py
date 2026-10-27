"""Assistenten: Fächerkreis für Operatoren (Päckchen AF, Schritt 2)

Revision ID: 0091
Revises: 0090
Create Date: 2026-10-27

**`assistants.operator_faecher`** (JSONB-Liste von Fach-Slugs, Vorgabe `[]`): Aus diesen Fächern
holt die Plattform die Definition eines Operators, den die Schülernachricht nennt, und setzt
sie als Abschnitt „Operator dieser Aufgabe" in den Systemtext. Leer heißt aus — bestehende
Assistenten ändern sich also nicht.

Slugs statt IDs, wie `subject` im YAML: Der Export soll in einer anderen Installation tragen.

**Rücknahme:** `alembic downgrade 0090` entfernt die Spalte samt Inhalt.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assistants",
        sa.Column("operator_faecher", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("assistants", "operator_faecher")
