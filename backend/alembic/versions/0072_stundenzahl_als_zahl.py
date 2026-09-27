"""Stundenzahl der Curriculum-Kapitel als Zahl statt als Text

Revision ID: 0072
Revises: 0071
Create Date: 2026-09-24

⚠️ **Warum eine Datenmigration.** `context_nodes.metadata` ist JSONB und erzwingt keinen
Typ. Der Curriculum-Entwurf führte `std` als Text, die Jahresplanung rechnet damit —
`max(0, zugewiesen - soll_std)` warf `TypeError` und die **ganze** Jahresübersicht
antwortete mit 500 (Befund Jan, 24.09.2026). Im Dev-Bestand waren 18 von 24 Kapiteln
betroffen.

Die Leser normalisieren seither selbst (`app/context/stunden.als_stundenzahl`), der
Schreibpfad ebenso. Diese Migration räumt den Bestand auf, damit die Daten die Zusage
auch dann tragen, wenn jemand sie an der Anwendung vorbei liest — Statistik, Export,
psql.

**Nur eindeutig Numerisches wird gewandelt.** Ein Wert wie `"12-14"` oder `"ca. 8"`
bleibt stehen: Daraus eine Zahl zu machen hieße, eine zu erfinden. Die Leser geben für
solche Werte `None` zurück, und die Oberfläche kann „keine Angabe" sagen — das ist wahr,
eine erfundene 12 wäre es nicht.
"""
from alembic import op

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


# `~ '^[0-9]+$'` statt eines Casts: Ein `::int` auf „ca. 8" bräche die Migration ab.
_BEDINGUNG = """
    metadata ? 'std'
    AND jsonb_typeof(metadata->'std') = 'string'
    AND metadata->>'std' ~ '^[0-9]+$'
"""


def upgrade() -> None:
    for typ in ("kapitel", "lernsequenz"):
        op.execute(f"""
            UPDATE context_nodes
            SET metadata = jsonb_set(
                metadata, '{{std}}', to_jsonb((metadata->>'std')::int)
            )
            WHERE content_type = '{typ}' AND {_BEDINGUNG}
        """)


def downgrade() -> None:
    """Zurück zu Text.

    Die Rückrichtung ist **verlustfrei für die Anwendung** — die Leser nehmen beides.
    Sie stellt allerdings nicht wieder her, welche Zeile vorher schon eine Zahl war;
    nach einem Hin und Her sind alle Text. Das ist hinnehmbar, weil genau dieser
    Unterschied der Fehler war.
    """
    for typ in ("kapitel", "lernsequenz"):
        op.execute(f"""
            UPDATE context_nodes
            SET metadata = jsonb_set(
                metadata, '{{std}}', to_jsonb((metadata->>'std'))
            )
            WHERE content_type = '{typ}'
              AND metadata ? 'std'
              AND jsonb_typeof(metadata->'std') = 'number'
        """)
