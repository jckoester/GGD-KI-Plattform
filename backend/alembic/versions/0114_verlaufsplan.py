"""Jahresverlaufsplan: Entwurf und ein Plan je Fach, Stufe und Schuljahr (Päckchen BD, Schritt 2)

Revision ID: 0114
Revises: 0113
Create Date: 2026-11-25

Der neue Knotentyp `verlaufsplan` selbst braucht keine Migration (`content_type` ist freier
Text). Zwei Dinge schon:

1. `check_context_nodes_draft_typ` erlaubt `draft` jetzt auch am `verlaufsplan` — er beginnt als
   Entwurf und wird von der Fachschaft beschlossen (BD F8). Die Leseregel für Entwürfe prüft
   den Status, nicht den Typ; sie gilt damit ohne Änderung.
2. `uq_context_nodes_verlaufsplan`: höchstens ein Plan je Fach, Jahrgangsstufe (`min_grade`)
   und Schuljahr (`metadata->>'schuljahr'`), gezählt über Entwurf und beschlossen.

**Rücknahme:** `alembic downgrade 0113` löscht vorhandene Verlaufspläne (es gibt keinen
Bestand vor diesem Release) und stellt die alte Bedingung her.
"""
import sqlalchemy as sa
from alembic import op

revision = "0114"
down_revision = "0113"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("check_context_nodes_draft_typ", "context_nodes", type_="check")
    op.create_check_constraint(
        "check_context_nodes_draft_typ",
        "context_nodes",
        "status <> 'draft' OR content_type IN ('curriculum','kapitel','lernsequenz','verlaufsplan')",
    )
    op.create_index(
        "uq_context_nodes_verlaufsplan",
        "context_nodes",
        ["subject_id", "min_grade", sa.text("(metadata ->> 'schuljahr')")],
        unique=True,
        postgresql_where=sa.text("content_type = 'verlaufsplan' AND status IN ('draft','active')"),
    )


def downgrade() -> None:
    op.drop_index("uq_context_nodes_verlaufsplan", table_name="context_nodes")
    # Kanten hängen per ON DELETE CASCADE an den Knoten.
    op.execute("DELETE FROM context_nodes WHERE content_type = 'verlaufsplan'")
    op.drop_constraint("check_context_nodes_draft_typ", "context_nodes", type_="check")
    op.create_check_constraint(
        "check_context_nodes_draft_typ",
        "context_nodes",
        "status <> 'draft' OR content_type IN ('curriculum','kapitel','lernsequenz')",
    )
