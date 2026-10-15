"""Tabelle `vorab_statistik`: Zähler der Vorab-Suche ohne Personenbezug (0.16, Schritt 3c)

Revision ID: 0086
Revises: 0085
Create Date: 2026-10-14

Je Kalenderwoche, Knoten, Stufe (`sicher` / `angebot`), Fach des Chats und Modell: wie oft ein
Baustein vorgelegt und — bei Angeboten — im Werkzeugergebnis derselben Antwort gefunden wurde;
dazu Wochenzeilen ohne Knoten mit den Nennern (Plan „Vorab-Suche-Begriffe" § 7.3, ADR-011
Teil 6.3). Kein Pseudonym, kein Bezug zu Konversation oder Nachricht.

⚠️ Der eindeutige Schlüssel steht mit **`NULLS NOT DISTINCT`** (Postgres ≥ 15): Fach, Knoten
und Stufe dürfen leer sein, und ohne die Klausel zählte `ON CONFLICT` dort nicht hoch, sondern
legte neue Zeilen an.

**Rücknahme:** `alembic downgrade 0085` entfernt die Tabelle samt Zählerständen. Nichts sonst
hängt an ihr.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None

ZAEHLER = (
    "vorgelegt", "im_werkzeugergebnis", "nachrichten", "mit_sicher", "mit_angebot",
    "angebot_nachgeschlagen", "suchen_ohne_angebot", "angebot_ohne_sicher",
    "angebot_ohne_sicher_nachgeschlagen",
)


def upgrade() -> None:
    op.create_table(
        "vorab_statistik",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("woche", sa.Date(), nullable=False),
        sa.Column("node_id", UUID(as_uuid=True),
                  sa.ForeignKey("context_nodes.id", ondelete="CASCADE"), nullable=True),
        sa.Column("stufe", sa.Text(), nullable=True),
        sa.Column("subject_id", sa.Integer(),
                  sa.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("modell", sa.Text(), nullable=False),
        *(sa.Column(z, sa.Integer(), nullable=False, server_default="0") for z in ZAEHLER),
        sa.UniqueConstraint("woche", "node_id", "stufe", "subject_id", "modell",
                            name="uq_vorab_statistik_schluessel",
                            postgresql_nulls_not_distinct=True),
        sa.CheckConstraint("stufe IN ('sicher', 'angebot')", name="check_vorab_statistik_stufe"),
        sa.CheckConstraint("(node_id IS NULL) = (stufe IS NULL)",
                           name="check_vorab_statistik_zeilenart"),
    )
    # Für die Kaskade beim Löschen eines Knotens — sonst ein Durchlauf je Löschung.
    op.create_index("idx_vorab_statistik_node", "vorab_statistik", ["node_id"])


def downgrade() -> None:
    op.drop_index("idx_vorab_statistik_node", table_name="vorab_statistik")
    op.drop_table("vorab_statistik")
