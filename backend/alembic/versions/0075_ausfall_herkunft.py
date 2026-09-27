"""Herkunft und Vorzustand eines Ausfalls an `lesson_slots`

Revision ID: 0075
Revises: 0074
Create Date: 2026-09-24

⚠️ **Warum zwei Spalten und nicht eine zweite Tabelle.** Rund ein Dutzend Stellen
entscheiden anhand von `lesson_slots.kategorie`, ob eine Stunde stattgefunden hat —
Stundenbilanz, sechs Stellen in den Verschiebe-Operationen, `jetzt.NICHT_GEHALTEN`, die
Sync-Zusammenfassung, dazu sechs im Frontend. Ein persönlicher Ausfall, der nur in einer
Nebentabelle stünde, wäre für all diese Stellen unsichtbar: Die Bilanz zählte die Stunde
weiter mit, der Verschiebe-Assistent sähe die Lücke nicht. Also bleibt es bei
`kategorie = 'ausfall'`; die Spalten hier sagen, **wer** das war und **was vorher
dastand**.

`ausfall_vorher` ist nötig, weil „vorher war Unterricht" nicht stimmt: Krankheit am
Klausurtag ist genau der Fall, in dem der Rückweg sonst die Prüfung verlöre.

**Keine Bedingung für die Paarung.** Naheliegend wäre `ausfall_herkunft IS NULL OR
kategorie = 'ausfall'`. Sie zerbräche am Snapshot-Restore (`app/planning/snapshots.py`):
Der schreibt `kategorie` aus einem JSON, das die Spalten nicht kennt — bei alten
Snapshots gäbe es sie dort nie. Die Leser prüfen deshalb selbst auf
`kategorie == 'ausfall'`; ein zurückgebliebener Wert ist dann folgenlos.
"""
import sqlalchemy as sa
from alembic import op

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None

_HERKUENFTE = "'stundenplan', 'eigen', 'assistent'"
_KATEGORIEN = "'unterricht', 'pruefung', 'ausfall', 'puffer', 'vertretung'"


def upgrade() -> None:
    op.add_column("lesson_slots", sa.Column("ausfall_herkunft", sa.Text(), nullable=True))
    op.add_column("lesson_slots", sa.Column("ausfall_vorher", sa.Text(), nullable=True))
    op.execute(
        "ALTER TABLE lesson_slots ADD CONSTRAINT check_lesson_slots_ausfall_herkunft "
        f"CHECK (ausfall_herkunft IS NULL OR ausfall_herkunft IN ({_HERKUENFTE}))"
    )
    op.execute(
        "ALTER TABLE lesson_slots ADD CONSTRAINT check_lesson_slots_ausfall_vorher "
        f"CHECK (ausfall_vorher IS NULL OR ausfall_vorher IN ({_KATEGORIEN}))"
    )
    # Bestand: Was heute `ausfall` ist, kam aus dem Stundenplan oder von Hand — das
    # lässt sich nicht mehr trennen. `stundenplan` ist die **vorsichtige** Annahme: Sie
    # lässt den Abgleich weiter über diese Slots bestimmen, statt ihm rückwirkend Slots
    # zu entziehen, die er selbst gesetzt hat.
    op.execute(
        "UPDATE lesson_slots SET ausfall_herkunft = 'stundenplan' "
        "WHERE kategorie = 'ausfall'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE lesson_slots DROP CONSTRAINT IF EXISTS "
               "check_lesson_slots_ausfall_vorher")
    op.execute("ALTER TABLE lesson_slots DROP CONSTRAINT IF EXISTS "
               "check_lesson_slots_ausfall_herkunft")
    op.drop_column("lesson_slots", "ausfall_vorher")
    op.drop_column("lesson_slots", "ausfall_herkunft")
