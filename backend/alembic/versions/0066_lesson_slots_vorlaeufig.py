"""`lesson_slots.vorlaeufig` — ein Termin, der noch nicht bestätigt ist

Zu Schuljahresbeginn planen Lehrkräfte das **Jahr**, der Stundenplan reicht aber nur bis
zum Halbjahreswechsel. Damit die Jahresplanung überhaupt Termine hat, wird das zweite
Halbjahr **vorläufig** aus dem Raster des ersten erzeugt. Diese Spalte hält fest, dass es
eine Annahme ist: Ein vorläufiger Termin darf ohne Rückfrage neu aufgebaut werden, ein
bestätigter nicht.

**Warum eine eigene Spalte und nicht `source`.** `source` beantwortet „woher kommt dieser
Termin" (`pattern` | `import` | `manual`), `vorlaeufig` beantwortet „ist er bestätigt". Ein
vorläufiger Slot ist weiterhin `source='pattern'` — beide Angaben sind unabhängig.

Die Alternative wäre gewesen, Vorläufigkeit daraus abzuleiten, dass das zweite Halbjahr
Slots aber kein eigenes Wochenmuster hat (der Generator fällt dann auf das Muster des
ersten zurück). Das wäre ein Invariant über zwei Tabellen, das nichts erzwingt — es bricht
in dem Moment, in dem jemand das Muster nach HJ2 kopiert.

Revision ID: 0066
Revises: 0065
"""
import sqlalchemy as sa
from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `false` für den Bestand: Was heute in der Datenbank steht, ist aus einem echten
    # Stundenplan oder von Hand entstanden — nichts davon ist eine Annahme.
    op.add_column(
        "lesson_slots",
        sa.Column(
            "vorlaeufig",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("lesson_slots", "vorlaeufig")
