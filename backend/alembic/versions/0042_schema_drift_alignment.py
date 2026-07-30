"""Schema-Drift zwischen Modellen und Datenbank angleichen

Zwei Altlasten, die `alembic check` (bzw. jedes `alembic revision --autogenerate`)
als Änderung meldet und dadurch jede neu generierte Migration verunreinigt:

1. ``assistants.created_by`` ist VARCHAR, das Modell deklariert ``Text``. In
   PostgreSQL sind VARCHAR ohne Längenangabe und TEXT gleichwertig — die Angleichung
   ist ein reiner Metadaten-Wechsel ohne Datenumschreibung.
2. ``user_preferences.preferences`` ist NULL-bar, obwohl Migration 0004 die Spalte als
   ``NOT NULL DEFAULT '{}'`` beschreibt. Ursache: 0004 legt die Tabelle mit
   ``CREATE TABLE IF NOT EXISTS`` an — sie existierte aber bereits aus 0001, sodass die
   Anweisung folgenlos blieb. Vor dem Setzen von NOT NULL werden etwaige NULL-Werte
   defensiv auf ``'{}'`` gehoben.

Die übrigen 19 Drift-Meldungen (14 Spalten ohne expliziten ``Text``-Typ, 6 nur per
Migration angelegte Indizes) wurden modellseitig in ``app/db/models.py`` behoben und
brauchen keine Migration.

Revision ID: 0042
Revises: 0041
"""

from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE assistants ALTER COLUMN created_by TYPE TEXT")
    op.execute("UPDATE user_preferences SET preferences = '{}'::jsonb WHERE preferences IS NULL")
    op.execute("ALTER TABLE user_preferences ALTER COLUMN preferences SET NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE user_preferences ALTER COLUMN preferences DROP NOT NULL")
    op.execute("ALTER TABLE assistants ALTER COLUMN created_by TYPE VARCHAR")
