"""Rückgängig im Curriculum-Editor: Tabelle `curriculum_snapshots` (0.46, Päckchen AP Teil B, Schritt 3)

Revision ID: 0108
Revises: 0107
Create Date: 2026-11-15

Ein Stand des Curriculum-Baums vor jedem Speichern im Editor und vor jedem Schreibstapel des
Assistenten (`app/context/curriculum_verlauf.py`). Verschwindet mit dem Curriculum (CASCADE).

**Rücknahme:** `alembic downgrade 0107` löscht die Tabelle samt Verlauf.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0108"
down_revision = "0107"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "curriculum_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("curriculum_id", UUID(as_uuid=True),
                  sa.ForeignKey("context_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("reason IN ('editor','assistant')", name="check_cs_reason"),
    )
    op.create_index("idx_curriculum_snapshots_cur", "curriculum_snapshots", ["curriculum_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_curriculum_snapshots_cur", table_name="curriculum_snapshots")
    op.drop_table("curriculum_snapshots")
