"""lesson_slots.source/external_uid, group_week_patterns.rhythmus (UP-8, Schritt 5)

Drei Felder, die der Stundenplan-Import braucht:

**`lesson_slots.source`** — woher ein Slot stammt: `'pattern'` (vom Generator aus dem
Wochenmuster), `'import'` (aus der Stundenplanquelle) oder `'manual'` (von Hand angelegt
oder geändert). Bestehende Slots bekommen `'pattern'`, denn genau daher kommen sie. Der
Wert trägt die Leitplanke aus dem Plan: **Ein Slot, der einmal `'manual'` war, wird vom
Sync nur noch gemeldet, nie geändert.**

**`lesson_slots.external_uid`** — die `lessonId` der Quelle.

> **Sie identifiziert die Unterrichts*reihe*, nicht die einzelne Stunde.** In der
> Aufzeichnung vom 06.08.2026 teilen sich fünf Perioden dieselbe `lessonId`; eindeutig je
> Periode ist nur deren `id`, die sich aber bei einem Neuimport des Stundenplans ändern
> kann. Die Identität eines Slots bleibt deshalb `(group_id, date, start_period)` — dafür
> gibt es `idx_lesson_slots_group_date`. `external_uid` beantwortet die andere Frage:
> **zu welcher Unterrichtsreihe** gehört dieser Slot. Wer sie für Zeilenidentität hält,
> baut Dubletten oder überschreibt fremde Stunden.

**`group_week_patterns.rhythmus`** — `'woechentlich'` (Vorgabe), `'a_woche'`, `'b_woche'`.

> Der bestehende Unique-Index `idx_gwp_unique` bleibt **ohne** `rhythmus`. Damit ist eine
> Slot-Position je Gruppe und Halbjahr genau einem Rhythmus zugeordnet. Das verhindert den
> widersprüchlichen Fall „wöchentlich **und** A-Woche" (der doppelt erzeugte Slots
> ergäbe). Preis: Eine Gruppe kann an derselben Position nicht in A- und B-Wochen
> unterschiedlich lange Stunden haben. Das ist exotisch; der widersprüchliche Fall wäre
> häufiger und teurer.

Revision ID: 0044
Revises: 0043
"""
from alembic import op
import sqlalchemy as sa

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lesson_slots",
        sa.Column(
            "source", sa.Text(), nullable=False, server_default=sa.text("'pattern'")
        ),
    )
    op.add_column("lesson_slots", sa.Column("external_uid", sa.Text(), nullable=True))
    op.create_check_constraint(
        "check_ls_source", "lesson_slots", "source IN ('pattern','import','manual')"
    )
    # Für den Abgleich „welche Slots gehören zu dieser Unterrichtsreihe?". Partiell, weil
    # die Spalte für alle vom Generator erzeugten Slots leer bleibt.
    op.create_index(
        "idx_lesson_slots_external",
        "lesson_slots",
        ["group_id", "external_uid"],
        postgresql_where=sa.text("external_uid IS NOT NULL"),
    )

    op.add_column(
        "group_week_patterns",
        sa.Column(
            "rhythmus",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'woechentlich'"),
        ),
    )
    op.create_check_constraint(
        "check_gwp_rhythmus",
        "group_week_patterns",
        "rhythmus IN ('woechentlich','a_woche','b_woche')",
    )


def downgrade() -> None:
    op.drop_constraint("check_gwp_rhythmus", "group_week_patterns", type_="check")
    op.drop_column("group_week_patterns", "rhythmus")
    op.drop_index("idx_lesson_slots_external", table_name="lesson_slots")
    op.drop_constraint("check_ls_source", "lesson_slots", type_="check")
    op.drop_column("lesson_slots", "external_uid")
    op.drop_column("lesson_slots", "source")
