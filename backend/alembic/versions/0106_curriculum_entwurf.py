"""Status `draft` für Curricula (0.45, Päckchen AP Teil A, E11)

Revision ID: 0106
Revises: 0105
Create Date: 2026-11-15

Erweitert `check_context_nodes_status` um `draft` und begrenzt ihn mit
`check_context_nodes_draft_typ` auf `curriculum`, `kapitel` und `lernsequenz` — ein Entwurf
anderer Typen hätte keine Regel, die ihn verbirgt (`app/context/curriculum_entwurf.py`).

**Rücknahme:** `alembic downgrade 0105` macht vorhandene Entwürfe zu archivierten Knoten
(`archived_at` = jetzt) — sie bleiben erhalten, erscheinen aber nirgends mehr als gültig.
"""
from alembic import op

revision = "0106"
down_revision = "0105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("check_context_nodes_status", "context_nodes", type_="check")
    op.create_check_constraint(
        "check_context_nodes_status",
        "context_nodes",
        "status IN ('active','archived','deleted','draft')",
    )
    op.create_check_constraint(
        "check_context_nodes_draft_typ",
        "context_nodes",
        "status <> 'draft' OR content_type IN ('curriculum','kapitel','lernsequenz')",
    )


def downgrade() -> None:
    op.drop_constraint("check_context_nodes_draft_typ", "context_nodes", type_="check")
    op.execute(
        "UPDATE context_nodes SET status = 'archived', archived_at = now() WHERE status = 'draft'"
    )
    op.drop_constraint("check_context_nodes_status", "context_nodes", type_="check")
    op.create_check_constraint(
        "check_context_nodes_status",
        "context_nodes",
        "status IN ('active','archived','deleted')",
    )
