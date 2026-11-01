"""Thema verknüpfter Termine nachziehen (Befund Prod, 01.11.2026)

Revision ID: 0096
Revises: 0095
Create Date: 2026-11-01

Die Jahresplanung zeigt `lesson_slots.thema`. Beim Anlegen eines Stundenentwurfs ohne Thema
blieb es leer, und die Übersicht zeigte „Thema eingeben …“ statt des Entwurfstitels. Seit dieser
Version folgt das Thema einem Umbenennen (`planning/router.py`, `patch_lesson`); diese Migration
füllt die leeren Themen verknüpfter Termine einmalig mit dem Titel des Entwurfs.

Nicht erfasst: Termine, die noch einen **alten** Titel tragen. Sie lassen sich von einem bewusst
anderen Thema nicht unterscheiden; sie ziehen beim nächsten Umbenennen des Entwurfs nach.

**Rücknahme:** `alembic downgrade 0095` ändert nichts zurück.
"""
from alembic import op

revision = "0096"
down_revision = "0095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE lesson_slots s
           SET thema = n.title
          FROM context_nodes n
         WHERE n.id = s.stunde_node_id
           AND n.content_type = 'unterrichtsstunde'
           AND (s.thema IS NULL OR btrim(s.thema) = '')
        """
    )


def downgrade() -> None:
    pass
