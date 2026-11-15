"""Status `upcoming` für Bildungsplan-Fassungen, die erst später gelten (0.46, Päckchen AP Teil B, F10)

Revision ID: 0107
Revises: 0106
Create Date: 2026-11-15

Der Import archivierte bisher jede Fassung, die im laufenden Schuljahr keine Stufe braucht —
auch die kommende. Damit konnte keine Fachschaft ihr Curriculum vor dem Wechsel schreiben, und
der Löschlauf hätte eine weit im Voraus importierte Fassung nach 1095 Tagen entfernt. Jetzt
setzt der Import `upcoming` (`app/context/editions.py`, `KUENFTIG`); nur Bildungsplan-Typen
dürfen ihn tragen.

Bestehende Daten ändert die Migration nicht: Welche archivierten Knoten eine kommende Fassung
sind, entscheidet der Fahrplan beim nächsten Import (`scripts/import_bildungsplan.py`).

**Rücknahme:** `alembic downgrade 0106` macht `upcoming` zu `archived` (`archived_at` = jetzt).
"""
from alembic import op

revision = "0107"
down_revision = "0106"
branch_labels = None
depends_on = None

_BP_TYPEN = (
    "'fachplan','leitidee','ik_kompetenz','pk_gruppe','pk_kompetenz','leitperspektive',"
    "'leitperspektive_aspekt','operator','lfdb_baustein','lfdb_themenblock','lfdb_kompetenz'"
)


def upgrade() -> None:
    op.drop_constraint("check_context_nodes_status", "context_nodes", type_="check")
    op.create_check_constraint(
        "check_context_nodes_status",
        "context_nodes",
        "status IN ('active','archived','deleted','draft','upcoming')",
    )
    op.create_check_constraint(
        "check_context_nodes_upcoming_typ",
        "context_nodes",
        f"status <> 'upcoming' OR content_type IN ({_BP_TYPEN})",
    )


def downgrade() -> None:
    op.drop_constraint("check_context_nodes_upcoming_typ", "context_nodes", type_="check")
    op.execute(
        "UPDATE context_nodes SET status = 'archived', archived_at = now() WHERE status = 'upcoming'"
    )
    op.drop_constraint("check_context_nodes_status", "context_nodes", type_="check")
    op.create_check_constraint(
        "check_context_nodes_status",
        "context_nodes",
        "status IN ('active','archived','deleted','draft')",
    )
