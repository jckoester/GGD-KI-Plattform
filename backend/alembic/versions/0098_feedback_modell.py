"""Rückmeldung nennt das Modell (0.28.1)

Revision ID: 0098
Revises: 0097
Create Date: 2026-11-02

**`feedback.model`** und **`feedback.provider_model`**: Alias und Anbietermodell der letzten
Antwort im Chat, aus dem die Meldung kam. Der Server liest beides aus der eigenen Konversation
der meldenden Person; gespeichert werden nur die Namen, kein Bezug zum Chat. Kein
Personenbezug, kein Inhalt — deshalb ohne Einwilligung, anders als der Chat-Anhang.

Bestehende Meldungen bleiben leer; aus einem vorhandenen Anhang ließe sich das Modell zwar
lesen, die Ansicht zeigt es dort aber ohnehin je Nachricht.

**Rücknahme:** `alembic downgrade 0097` entfernt beide Spalten.
"""
from alembic import op
import sqlalchemy as sa

revision = "0098"
down_revision = "0097"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("feedback", sa.Column("model", sa.Text(), nullable=True))
    op.add_column("feedback", sa.Column("provider_model", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("feedback", "provider_model")
    op.drop_column("feedback", "model")
