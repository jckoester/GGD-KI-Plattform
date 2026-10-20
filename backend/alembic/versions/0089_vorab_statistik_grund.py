"""Vorab-Statistik: warum ein Knoten vorlag — Spalte `grund` (0.20, Päckchen AC, Schritt 5)

Revision ID: 0089
Revises: 0088
Create Date: 2026-10-20

**`grund`** sagt bei einer Knotenzeile, *warum* der Knoten in seiner Stufe stand: leer wie bisher
(Name oder Distanz), `gruppe` — ein Begriff aus dem Graubereich, sicher geworden, weil die
Unterrichtsgruppe ihn eingeführt hat (F2 a, Jan 20.10.2026) —, und ab Schritt 6 `block` für
die Titel der Block-Zeile „In dieser Gruppe bereits eingeführt". So lässt sich im Betrieb
prüfen, ob der Stufenwechsel Fehltreffer bringt.

Eigene Spalte statt neuer Werte in `stufe` (Jan, 20.10.2026, Weg a): Jede Auswertung, die nach
`stufe = 'sicher'` fragt, bleibt richtig. `grund` gehört zum Schlüssel — sonst zählten
„sicher" und „sicher wegen der Gruppe" in dieselbe Zeile. Wochenzeilen haben keinen Grund.

**Rücknahme:** `alembic downgrade 0088` fasst die Zeilen je alter Schlüssel zusammen (Summe der
Zähler), stellt den alten Schlüssel wieder her und entfernt die Spalte.
"""
from alembic import op
import sqlalchemy as sa

revision = "0089"
down_revision = "0088"
branch_labels = None
depends_on = None

_ZAEHLER = (
    "vorgelegt", "im_werkzeugergebnis", "nachrichten", "mit_sicher", "mit_angebot",
    "angebot_nachgeschlagen", "suchen_ohne_angebot", "angebot_ohne_sicher",
    "angebot_ohne_sicher_nachgeschlagen",
)


def upgrade() -> None:
    op.add_column("vorab_statistik", sa.Column("grund", sa.Text(), nullable=True))
    op.create_check_constraint(
        "check_vorab_statistik_grund", "vorab_statistik",
        "grund IS NULL OR (grund IN ('gruppe', 'block') AND node_id IS NOT NULL)",
    )
    op.drop_constraint("uq_vorab_statistik_schluessel", "vorab_statistik", type_="unique")
    op.execute(
        "ALTER TABLE vorab_statistik ADD CONSTRAINT uq_vorab_statistik_schluessel "
        "UNIQUE NULLS NOT DISTINCT (woche, node_id, stufe, grund, subject_id, modell)"
    )


def downgrade() -> None:
    summen = ", ".join(f"sum({z}) AS {z}" for z in _ZAEHLER)
    op.execute(f"""
        CREATE TEMP TABLE _vs AS
        SELECT min(id) AS id, woche, node_id, stufe, subject_id, modell, {summen}
        FROM vorab_statistik GROUP BY woche, node_id, stufe, subject_id, modell
    """)
    op.execute("DELETE FROM vorab_statistik")
    op.execute(f"""
        INSERT INTO vorab_statistik (id, woche, node_id, stufe, subject_id, modell, {", ".join(_ZAEHLER)})
        SELECT * FROM _vs
    """)
    op.execute("DROP TABLE _vs")
    op.drop_constraint("uq_vorab_statistik_schluessel", "vorab_statistik", type_="unique")
    op.drop_constraint("check_vorab_statistik_grund", "vorab_statistik", type_="check")
    op.drop_column("vorab_statistik", "grund")
    op.execute(
        "ALTER TABLE vorab_statistik ADD CONSTRAINT uq_vorab_statistik_schluessel "
        "UNIQUE NULLS NOT DISTINCT (woche, node_id, stufe, subject_id, modell)"
    )
