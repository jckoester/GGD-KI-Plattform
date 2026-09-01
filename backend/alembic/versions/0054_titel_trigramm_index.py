"""Trigramm-Index für die Teilsuche in Bausteinnamen

Das Nachschlagen (Migration 0053) findet einen Baustein nur unter seinem **ganzen**
Namen. Beschreibende Titel — „Anleitung zur Verwendung des Operators ‚nennen'" — trifft
so niemand: Wer sie sucht, tippt einen Ausschnitt.

Dieser Index macht die zweite Stufe der Identifikation möglich (ADR-017): Ähnlichkeit
über Trigramme, klar nachgeordnet hinter dem exakten Treffer.

⚠️ **Derselbe Ausdruck wie in 0053.** Der Index liegt auf dem normalisierten Titel
(ohne Gliederungsnummer, klein, einfache Leerzeichen) und kommt aus derselben Funktion
wie die Abfrage (`app.context.lookup.titel_normalisiert_sql`). Weicht er ab, benutzt
PostgreSQL ihn nicht — stillschweigend, ohne Fehler, nur langsamer.

`pg_trgm` ist eine Standard-Erweiterung; `CREATE EXTENSION` verlangt allerdings
Superuser-Rechte. In der Compose läuft die Datenbank als `postgres`, dort ist das
gegeben — bei einer verwalteten Datenbank ohne Superuser muss die Erweiterung vorab
vom Betreiber freigeschaltet werden.

Revision ID: 0054
Revises: 0053
"""

from alembic import op

from app.context.lookup import titel_normalisiert_sql

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None

INDEXNAME = "idx_context_nodes_titel_trigramm"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        f"CREATE INDEX {INDEXNAME} ON context_nodes "
        f"USING gin (({titel_normalisiert_sql('title')}) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEXNAME}")
    # Die Erweiterung bleibt: Sie kostet nichts und könnte anderswo in Gebrauch sein.
