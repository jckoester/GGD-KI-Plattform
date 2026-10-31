"""Zug-Auslöser: Treffer und gesetzte Anweisungen (0.26, Rückfall Schritt 10)

Revision ID: 0094
Revises: 0093
Create Date: 2026-10-31

**`zug_ausloeser`**: je Schülernachricht, bei der ein Zug-Auslöser (`app/pedagogy/druck.py`)
anschlug, eine Zeile — Art (`druck` | `lehrkraft`), Quelle der Erkennung, ob die Anweisung gesetzt
wurde und die wievielte Schülernachricht des Gesprächs es war. **Kein Text**, keine Person; die
Zeile hängt am Gespräch und geht mit ihm (CASCADE, Lebenszyklus der Konversation).

Zwei Zwecke: Der Nachsetz-Auslöser sieht hier, ob eine der beiden vorherigen Nachrichten Druck war
(ohne sie neu einzubetten), und der Betatest zählt, wie oft je 100 Gespräche eine Anweisung
gesetzt wird und ob die Schüler:in danach weiterarbeitet (`scripts/zug_ausloeser_statistik.py`).

**Rücknahme:** `alembic downgrade 0093` entfernt die Tabelle samt Inhalt.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0094"
down_revision = "0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "zug_ausloeser",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nutzer_nachricht", sa.Integer(), nullable=False),
        sa.Column("art", sa.Text(), nullable=False),
        sa.Column("quelle", sa.Text(), nullable=True),
        sa.Column("treffer", sa.Boolean(), nullable=False),
        sa.Column("anweisung", sa.Boolean(), nullable=False),
        sa.Column("erstellt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_zug_ausloeser_conversation", "zug_ausloeser", ["conversation_id"])
    op.create_index("ix_zug_ausloeser_erstellt", "zug_ausloeser", ["erstellt"])


def downgrade() -> None:
    op.drop_index("ix_zug_ausloeser_erstellt", table_name="zug_ausloeser")
    op.drop_index("ix_zug_ausloeser_conversation", table_name="zug_ausloeser")
    op.drop_table("zug_ausloeser")
