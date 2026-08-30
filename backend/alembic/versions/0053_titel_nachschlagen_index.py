"""Ausdrucksindex für das Nachschlagen benannter Knoten

Die Suche schlägt seit 08/2026 zuerst nach, ob die Anfrage einen Knoten **benennt** —
„Operator nennen" findet damit den Operator *nennen* statt *erkennen* und *korrigieren*.
Der Abgleich läuft gegen den normalisierten Titel (ohne Gliederungsnummer, klein,
einfache Leerzeichen), und dieser Ausdruck ist ohne Index für jede der 14.244 Zeilen neu
zu berechnen.

Gemessen am 30.08.2026:

============================  ==========
Nachschlage-Abfrage            Laufzeit
============================  ==========
ohne Index (Seq Scan)            18,5 ms
mit Ausdrucksindex                0,1 ms
============================  ==========

Der Index kostet 1,8 MB und baut in 0,1 s. Der Gewinn fällt bei **jeder** Suche an, nicht
nur bei Nachschlage-Anfragen: Ob die Anfrage einen Namen meint, weiß man erst nach der
Abfrage.

⚠️ **Der Ausdruck muss zeichengenau dem der Abfrage entsprechen**, sonst benutzt
PostgreSQL den Index nicht — stillschweigend, ohne Fehler, nur langsamer. Deshalb kommt
er aus derselben Funktion wie dort (`app.context.lookup.titel_normalisiert_sql`) statt
hier abgeschrieben zu werden.

Revision ID: 0053
Revises: 0052
"""

from alembic import op

from app.context.lookup import titel_normalisiert_sql

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

INDEXNAME = "idx_context_nodes_titel_nachschlagen"


def upgrade() -> None:
    op.execute(
        f"CREATE INDEX {INDEXNAME} ON context_nodes ({titel_normalisiert_sql('title')})"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEXNAME}")
