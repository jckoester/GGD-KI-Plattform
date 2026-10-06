"""Tabelle `message_context_nodes`: die Bausteine einer Antwort (0.14, Schritt 2)

Revision ID: 0083
Revises: 0082
Create Date: 2026-10-06

Je Assistenten-Nachricht die Bausteine, die beim Antworten vorlagen — aus der Vorab-Suche
(`vorab`) oder aus einer Suchrunde des Modells (`werkzeug`). Grundlage der Zeile
„Kontext (n)" unter der Antwort (Plan „Bausteine zur Antwort", 27.09.2026).

Löschkaskade auf beiden Seiten: mit der Nachricht (90-Tage-Regel, Löschen der
Konversation) und mit dem Baustein. Kein zusätzlicher Personenbezug — die Nachricht
gehört schon heute einem Pseudonym.

**Rücknahme:** `alembic downgrade 0082` entfernt die Tabelle samt Inhalt. Antworten bleiben
unberührt; nur ihre Kontextzeile fehlt danach.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "message_context_nodes",
        sa.Column("message_id", UUID(as_uuid=True),
                  sa.ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("node_id", UUID(as_uuid=True),
                  sa.ForeignKey("context_nodes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("herkunft", sa.Text(), nullable=False),
        sa.Column("aehnlichkeit", sa.Float(), nullable=True),
        sa.CheckConstraint("herkunft IN ('vorab', 'werkzeug')",
                           name="check_message_context_nodes_herkunft"),
    )
    # Für die Kaskade beim Löschen eines Bausteins — sonst ein Durchlauf je Löschung.
    op.create_index("idx_message_context_nodes_node", "message_context_nodes", ["node_id"])


def downgrade() -> None:
    op.drop_index("idx_message_context_nodes_node", table_name="message_context_nodes")
    op.drop_table("message_context_nodes")
