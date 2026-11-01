"""Assistenten-Pflege (0.27, Päckchen D)

Revision ID: 0095
Revises: 0094
Create Date: 2026-11-01

**Fach aus der Gruppe** (Plan F2 a): Bei Gruppen-Scope (`teaching_group`, `subject_department`,
`activity_group`) trägt ein Assistent das Fach seiner Gruppe. Seit 0.27 setzt der Server es so;
diese Migration bereinigt den Bestand mit derselben Regel. Gruppen ohne Fach (AG) bleiben
unberührt.

**Rücknahme:** `alembic downgrade 0094` ändert nichts zurück — das frühere Fach ist nicht
gespeichert, und es widersprach der Gruppe.
"""
from alembic import op

revision = "0095"
down_revision = "0094"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE assistants a
           SET subject_id = g.subject_id
          FROM groups g
         WHERE g.id = a.scope_group_id
           AND a.scope IN ('teaching_group', 'subject_department', 'activity_group')
           AND g.subject_id IS NOT NULL
           AND a.subject_id IS DISTINCT FROM g.subject_id
        """
    )


def downgrade() -> None:
    pass
