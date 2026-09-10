"""`conversation_flags.last_reminder_at` — wann zuletzt an diesen Fall erinnert wurde.

Zwei Aufgaben für eine Spalte:

1. **Nicht täglich erinnern.** Der Erinnerungslauf läuft täglich; ohne einen Vermerk
   bekäme dasselbe Postfach jeden Morgen dieselbe Liste, und nach der dritten Woche
   liest sie niemand mehr.

2. **Nicht ohne Vorwarnung löschen.** Ein offenes Flag schützte die Konversation
   bisher **unbefristet** — genau das lässt 1.0-Kriterium 3 offen. Mit der
   Obergrenze fällt der Schutz, aber erst, wenn mindestens einmal erinnert wurde.
   Die Kopplung ist Absicht: Läuft der Erinnerungslauf nicht, wird auch nicht
   gelöscht. Ungefragt zu löschen wäre der schlechtere Ausfall als zu lange
   aufzubewahren.

`NULL` heißt „noch nie erinnert" — der Zustand aller Bestandszeilen.

Revision ID: 0059
Revises: 0058
"""
from alembic import op
import sqlalchemy as sa

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_flags",
        sa.Column("last_reminder_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    # Teilindex auf die unerledigten Fälle: Der tägliche Lauf fragt genau danach,
    # und sie sind eine verschwindende Minderheit der Zeilen.
    op.create_index(
        "idx_flags_offen_flagged_at",
        "conversation_flags",
        ["flagged_at"],
        postgresql_where=sa.text("status IN ('open', 'under_review')"),
    )


def downgrade() -> None:
    op.drop_index("idx_flags_offen_flagged_at", table_name="conversation_flags")
    op.drop_column("conversation_flags", "last_reminder_at")
