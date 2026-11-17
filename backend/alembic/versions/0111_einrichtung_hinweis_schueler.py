"""Site-Text „Hinweis in der Einrichtung“ für Schüler:innen (0.47, F7 a)

Revision ID: 0111
Revises: 0110
Create Date: 2026-11-17

Legt die leere Zeile `einrichtung_hinweis_schueler` in `site_config` an — der Admin-Endpunkt
überschreibt nur vorhandene Schlüssel. Leer heißt: Die Einrichtung der Schüler:innen zeigt keinen
Hinweis der Schule. Der Hinweis an Lehrkräfte bleibt `einrichtung_hinweis` (0105).

**Rücknahme:** `alembic downgrade 0110` entfernt die Zeile samt Text.
"""
from alembic import op

revision = "0111"
down_revision = "0110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO site_config (key, value) VALUES ('einrichtung_hinweis_schueler', NULL) "
        "ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM site_config WHERE key = 'einrichtung_hinweis_schueler'")
