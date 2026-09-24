"""Jahrgang an der Unterrichtsgruppe — für Gruppen ohne Klasse

Revision ID: 0073
Revises: 0072
Create Date: 2026-09-24

⚠️ **Warum eine eigene Spalte.** Der Jahrgang kam bisher ausschließlich über
`group_source_classes` aus dem Klassennamen. Gruppen aus dem Stundenplan und
Kursstufenkurse haben dort nichts — gemessen am 24.09.2026 blieb für `ch-tl-abi28` und
`nwt-tl-10abcd` der Jahrgang unbekannt, und die Curriculum-Auflösung bot daraufhin
**alle** Curricula des Fachs an: einem Abi-28-Kurs also „CH Kl. 8".

**Nullable mit Absicht.** „Unbekannt" ist ein echter Zustand, kein Platzhalter: Wo weder
Klasse noch Namensmuster etwas hergeben, soll die Oberfläche das sagen können, statt eine
Zahl zu erfinden.

**Kein Backfill.** Die Leseseite leitet aus dem Namen ab, solange die Spalte leer ist
(`app/groups/jahrgang.py`) — Altgruppen funktionieren also sofort. Ein Backfill würde die
Ableitung von heute einfrieren; so bleibt sie eine Vermutung, die sich mitverbessert, bis
ein Mensch entscheidet.
"""
import sqlalchemy as sa
from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("groups", sa.Column("jahrgang", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("groups", "jahrgang")
