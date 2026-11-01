"""Assistenten-Pflege (0.27, Päckchen D)

Revision ID: 0095
Revises: 0094
Create Date: 2026-11-01

**Fach aus der Gruppe** (Plan F2 a): Bei Gruppen-Scope (`teaching_group`, `subject_department`,
`activity_group`) trägt ein Assistent das Fach seiner Gruppe. Seit 0.27 setzt der Server es so;
diese Migration bereinigt den Bestand mit derselben Regel. Gruppen ohne Fach (AG) bleiben
unberührt.

**Scope „Jahrgang“ (`grade`) entfällt** (Plan F1): Seit 0.22 wirken die Klassenstufen bei
jeder Freigabe; „Jahrgang“ war dasselbe wie „Alle Schüler:innen“ mit Stufen. `grade` wird zu
`all_students` (auch in `scope_pending`), die Stufen bleiben. Ohne Stufen hieß „Jahrgang“
seit 0.22 schon „alle Jahrgänge“ (`sichtbarkeit.py` prüft nur gesetzte Grenzen) — die
Umstellung ändert also für keinen Assistenten, wer ihn sieht. Die Check-Constraints kennen
`grade` danach nicht mehr.

**Rücknahme:** `alembic downgrade 0094` nimmt `grade` wieder in die Constraints auf. Die Daten
bleiben, wie sie sind: Welcher Assistent „Jahrgang“ hieß, ist nicht gespeichert, und das
Fach widersprach der Gruppe.
"""
from alembic import op

revision = "0095"
down_revision = "0094"
branch_labels = None
depends_on = None


_ALT = ("'private','subject_department','teachers','activity_group',"
        "'teaching_group','grade','all_students','all'")
_NEU = ("'private','subject_department','teachers','activity_group',"
        "'teaching_group','all_students','all'")


def _constraints(werte: str) -> None:
    op.drop_constraint("check_assistant_scope", "assistants", type_="check")
    op.drop_constraint("check_assistant_scope_pending", "assistants", type_="check")
    op.create_check_constraint("check_assistant_scope", "assistants", f"scope IN ({werte})")
    op.create_check_constraint(
        "check_assistant_scope_pending", "assistants",
        f"scope_pending IS NULL OR scope_pending IN ({werte})",
    )


def upgrade() -> None:
    op.execute("UPDATE assistants SET scope = 'all_students' WHERE scope = 'grade'")
    op.execute("UPDATE assistants SET scope_pending = 'all_students' WHERE scope_pending = 'grade'")
    _constraints(_NEU)
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
    _constraints(_ALT)
