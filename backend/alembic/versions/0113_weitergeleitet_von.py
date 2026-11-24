"""Aufgaben-Weiterleitung: Ausgangsmodell an der Antwort (Plan „Freier Schüler-Chat“, 7a)

Revision ID: 0113
Revises: 0112
Create Date: 2026-11-24

`messages.weitergeleitet_von`: Hat der Aufgaben-Klassifikator einen Zug an das Zielmodell
weitergeleitet, steht hier das Modell, das sonst geantwortet hätte; `model` trägt das
tatsächliche. Die Oberfläche setzt daran keinen Trenner für einen solchen Wechsel, und der Anteil
weitergeleiteter Züge lässt sich zählen. Leer für alle Bestandszeilen.

**Rücknahme:** `alembic downgrade 0112` entfernt die Spalte samt Inhalt.
"""
import sqlalchemy as sa
from alembic import op

revision = "0113"
down_revision = "0112"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("weitergeleitet_von", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "weitergeleitet_von")
