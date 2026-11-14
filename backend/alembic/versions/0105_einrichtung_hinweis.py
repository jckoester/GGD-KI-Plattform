"""Site-Text „Hinweis in der Einrichtung“ (0.43, Onboarding für Lehrkräfte, F9 b)

Revision ID: 0105
Revises: 0104
Create Date: 2026-11-14

Legt die leere Zeile `einrichtung_hinweis` in `site_config` an — der Admin-Endpunkt überschreibt
nur vorhandene Schlüssel. Leer heißt: Die Einrichtung zeigt keinen Hinweis der Schule.

**Rücknahme:** `alembic downgrade 0104` entfernt die Zeile samt Text.
"""
from alembic import op

revision = "0105"
down_revision = "0104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO site_config (key, value) VALUES ('einrichtung_hinweis', NULL) "
        "ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM site_config WHERE key = 'einrichtung_hinweis'")
