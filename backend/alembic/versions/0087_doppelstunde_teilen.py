"""Doppelstunde teilen: `lesson_slots.geteilt` + ein Entwurf hängt an höchstens einem Termin (0.19, Schritt 3)

Revision ID: 0087
Revises: 0086
Create Date: 2026-10-20

**`geteilt`** markiert die beiden Hälften einer geteilten Doppelstunde. Die Herkunft
(`source`) bleibt dabei stehen — der Stundenplan-Abgleich ordnet jede Stunde einzeln zu und
bringt Ausfälle weiter auf beide Hälften (Plan F4 (b), Jan 19.10.2026). Der Neuaufbau aus
dem Wochenmuster lässt geteilte Termine stehen, statt wieder eine Doppelstunde darüberzulegen.

**Eindeutigkeit von `stunde_node_id`**: Ein Stundenentwurf hängt an höchstens einem Termin.
`get_lesson` und `get_lesson_detail` lesen den Termin mit `scalar_one_or_none` und brächen bei zweien mit `MultipleResultsFound` ab — beim Teilen bleibt der Entwurf deshalb an der ersten
Hälfte. Gibt es schon doppelte Zuordnungen, bricht die Migration mit einer
Liste ab, statt sie still aufzulösen: Welcher Termin den Entwurf behält, entscheidet ein
Mensch.

⚠️ **Als Constraint `DEFERRABLE INITIALLY DEFERRED`, nicht als Index.** Verschieben und Tauschen
(`operations.py`, `swap`) setzen den Entwurf am Ziel, bevor sie ihn an der Quelle lösen — für
einen Augenblick hängt er innerhalb der Transaktion an zwei Terminen. Ein sofort geprüfter Index
brach daran 22 Integrationstests (erster Entwurf, 20.10.2026); geprüft wird deshalb beim Commit.
Mehrere `NULL` sind erlaubt (Postgres: `NULLS DISTINCT`).

Vorab prüfen:

    SELECT stunde_node_id, count(*) FROM lesson_slots
    WHERE stunde_node_id IS NOT NULL GROUP BY 1 HAVING count(*) > 1;

**Rücknahme:** `alembic downgrade 0086` entfernt Constraint und Spalte. Geteilte Hälften bleiben
zwei Einzelstunden (ohne Markierung) — der nächste Neuaufbau aus dem Muster würde sie dann
wieder überdecken.
"""
from alembic import op
import sqlalchemy as sa

revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    doppelt = op.get_bind().execute(sa.text(
        "SELECT stunde_node_id, count(*) FROM lesson_slots "
        "WHERE stunde_node_id IS NOT NULL GROUP BY 1 HAVING count(*) > 1"
    )).fetchall()
    if doppelt:
        liste = ", ".join(f"{z[0]} ({z[1]}×)" for z in doppelt)
        raise RuntimeError(
            "Migration 0087: Diese Stundenentwürfe hängen an mehreren Terminen — "
            f"{liste}. Bitte je Entwurf alle Termine bis auf einen lösen "
            "(UPDATE lesson_slots SET stunde_node_id = NULL WHERE id = …) und neu starten."
        )
    op.add_column(
        "lesson_slots",
        sa.Column("geteilt", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_unique_constraint(
        "uq_lesson_slots_stunde_node_id",
        "lesson_slots",
        ["stunde_node_id"],
        deferrable=True,
        initially="DEFERRED",
    )


def downgrade() -> None:
    op.drop_constraint("uq_lesson_slots_stunde_node_id", "lesson_slots", type_="unique")
    op.drop_column("lesson_slots", "geteilt")
