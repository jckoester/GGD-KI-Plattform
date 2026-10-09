"""Spalte `conversations.stunde_node_id`: der Stundenbezug einer Konversation (0.15, Schritt 2)

Revision ID: 0084
Revises: 0083
Create Date: 2026-10-09

Eine Konversation kann sich auf eine Unterrichtsstunde beziehen — gesetzt beim Anlegen aus
der Entwurfsansicht (Plan „Stundenentwurfs-Assistent", F4). Der Assistent bekommt die
Stunde als Systemzeile, die Stundenwerkzeuge nehmen sie als Vorgabe.

`ON DELETE SET NULL`: Verschwindet die Stunde, bleibt die Konversation — nur ohne Bezug.

**Rücknahme:** `alembic downgrade 0083` entfernt Spalte und Index. Konversationen bleiben;
gesetzte Bezüge gehen verloren.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("stunde_node_id", UUID(as_uuid=True),
                  sa.ForeignKey("context_nodes.id", ondelete="SET NULL"), nullable=True),
    )
    # Für das `SET NULL` beim Löschen eines Knotens — sonst ein Durchlauf je Löschung.
    op.create_index(
        "idx_conversations_stunde_node_id", "conversations", ["stunde_node_id"],
        postgresql_where=sa.text("stunde_node_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_conversations_stunde_node_id", table_name="conversations")
    op.drop_column("conversations", "stunde_node_id")
