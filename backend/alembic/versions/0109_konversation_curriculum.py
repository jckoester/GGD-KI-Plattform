"""Curriculumbezug einer Konversation (0.46, Päckchen AP Teil B, Schritt 6)

Revision ID: 0109
Revises: 0108
Create Date: 2026-11-16

`conversations.curriculum_node_id`: das Curriculum, an dem der Curriculum-Assistent arbeitet —
gesetzt aus dem Editor („Mit dem Assistenten bearbeiten") oder im Gespräch
(`waehle_curriculum`, `lege_curriculum_an`). Wie `stunde_node_id` eine Vorgabe für die
Funktionen, keine Erlaubnis. Wird das Curriculum gelöscht, fällt der Bezug weg (SET NULL).

**Rücknahme:** `alembic downgrade 0108` entfernt Spalte und Index.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0109"
down_revision = "0108"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column(
        "curriculum_node_id", UUID(as_uuid=True),
        sa.ForeignKey("context_nodes.id", ondelete="SET NULL"), nullable=True))
    op.create_index("idx_conversations_curriculum_node_id", "conversations", ["curriculum_node_id"],
                    postgresql_where=sa.text("curriculum_node_id IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("idx_conversations_curriculum_node_id", table_name="conversations")
    op.drop_column("conversations", "curriculum_node_id")
