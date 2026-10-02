"""Tabelle `system_spend`: Verbrauch der Plattform selbst, je Tag (0.12, Paket 2, AP3)

Revision ID: 0082
Revises: 0081
Create Date: 2026-10-02

Einbettungen für Suche, Import und Backfill gehören keiner Person und tauchten deshalb
in keiner Auskunft auf. Ihr Betrag wird jetzt je Tag aufsummiert und in `/budget` und
`/statistics/costs` als eigene Zeile „System" gezeigt — ohne Verrechnung gegen ein
Nutzerbudget. Kein Personenbezug.

**Rücknahme:** `alembic downgrade 0081` entfernt die Tabelle samt Inhalt. Die Einbettungen
laufen weiter; nur ihr Betrag wird nicht mehr festgehalten.
"""
from alembic import op
import sqlalchemy as sa

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_spend",
        sa.Column("tag", sa.Date(), primary_key=True),
        sa.Column("kosten_usd", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("anfragen", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_table("system_spend")
