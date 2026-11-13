"""Produkte im Chat: Konversation ↔ Produkt (0.41, Päckchen AN, Schritt 10, F2 a)

Revision ID: 0104
Revises: 0103
Create Date: 2026-11-13

Wie `chat_context_nodes` für Bausteine: Ein Produkt aus der eigenen Werkstatt hängt an einer
Konversation, der Chat legt seine Quelle bei jeder Frage bei (mit Längengrenze). Löschkaskade
auf **beiden** Seiten — verschwindet das Produkt, fällt der Anhang weg, die Konversation bleibt.

**Rücknahme:** `alembic downgrade 0103` entfernt die Tabelle samt Anhängen.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0104"
down_revision = "0103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_artifacts",
        sa.Column("chat_id", UUID(as_uuid=True),
                  sa.ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("artifact_id", UUID(as_uuid=True),
                  sa.ForeignKey("artifacts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("added_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
    )
    # Löschen eines Produkts sucht die Anhänge über `artifact_id`.
    op.create_index("idx_chat_artifacts_artifact", "chat_artifacts", ["artifact_id"])


def downgrade() -> None:
    op.drop_index("idx_chat_artifacts_artifact", table_name="chat_artifacts")
    op.drop_table("chat_artifacts")
