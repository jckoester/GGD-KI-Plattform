"""Geprüfter Vorschlag des Curriculum-Assistenten (0.46, Päckchen AP Teil B, Schritt 7)

Revision ID: 0110
Revises: 0109
Create Date: 2026-11-16

`conversations.curriculum_vorschlag`: der zuletzt erfolgreich geprüfte Stapel
(`preview_curriculum_operations`) mit Curriculum und Stand. Nach der Zustimmung schreibt
`apply_curriculum_operations` ohne Operationen genau diesen Stapel — die Funktionsantworten
früherer Nachrichten bleiben nicht im Verlauf, das Modell müsste ihn sonst neu bauen.

**Rücknahme:** `alembic downgrade 0109` entfernt die Spalte.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0110"
down_revision = "0109"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("curriculum_vorschlag", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "curriculum_vorschlag")
