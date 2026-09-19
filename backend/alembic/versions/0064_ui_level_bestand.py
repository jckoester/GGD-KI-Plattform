"""Bestandsnutzer:innen behalten ihre gewohnte Oberfläche (Darstellungsstufen)

Die Oberfläche startet künftig schmal und wird von der Nutzer:in selbst erweitert
(`preferences.ui_level`). Für alle, die die Plattform **heute schon benutzen**, wäre das
ein Rückschritt: Funktionen, mit denen sie arbeiten, verschwänden über Nacht aus der
Navigation. Diese Migration setzt sie deshalb einmalig auf die höchste Stufe ihrer Rolle.

**Warum die Zahlen hier fest stehen.** Der Zuschnitt liegt in `config/ui_levels.yaml` und
ist absichtlich ohne Release änderbar. Eine Migration darf ihn trotzdem nicht lesen: Sie
beschreibt einen **historischen Zustand** und muss in fünf Jahren dasselbe tun wie heute —
auch wenn die Datei dann anders aussieht oder fehlt. Deshalb der Stand vom 19.09.2026:
Lehrkraft vier Stufen, Schüler:in zwei.

Kommt später eine fünfte Lehrkraft-Stufe hinzu, bleiben die hier Nachgefüllten auf vier.
Das ist gewollt: Eine neue Stufe ist neue Funktionalität, und sie unangekündigt
einzublenden ist genau das, was die Stufen vermeiden sollen.

**Kein Schemawechsel.** `user_preferences.preferences` ist JSONB; der Schlüssel kommt
hinzu. Wer noch keine Zeile hat, bekommt eine — die Nutzer:innen stehen in
`pseudonym_audit`, das seit dem ersten Login je eine Zeile führt.

Rückwärts wird der Schlüssel wieder entfernt; alles andere in `preferences` bleibt
unangetastet.

Revision ID: 0064
Revises: 0063
"""
from alembic import op
import sqlalchemy as sa

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None

# Stand 19.09.2026 — siehe Docstring, bewusst nicht aus der Konfiguration gelesen.
HOECHSTE_STUFE = {"teacher": 4, "student": 2}


def upgrade() -> None:
    for rolle, stufe in HOECHSTE_STUFE.items():
        op.execute(sa.text("""
            INSERT INTO user_preferences (pseudonym, preferences)
            SELECT a.pseudonym, jsonb_build_object('ui_level', :stufe)
            FROM pseudonym_audit a
            WHERE a.role = :rolle
            ON CONFLICT (pseudonym) DO UPDATE
              SET preferences = user_preferences.preferences
                                || jsonb_build_object('ui_level', :stufe)
        """).bindparams(stufe=stufe, rolle=rolle))


def downgrade() -> None:
    op.execute("UPDATE user_preferences SET preferences = preferences - 'ui_level'")
