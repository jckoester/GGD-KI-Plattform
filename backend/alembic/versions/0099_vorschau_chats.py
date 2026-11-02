"""Vorschau-Chats und Rückmeldungen aus der Vorschau (0.29, Päckchen S, ADR-016)

Revision ID: 0099
Revises: 0098
Create Date: 2026-11-02

**`conversations.preview_context`** (F2 a): gesetzt, wenn der Chat in der Vorschau entstand —
mit dem simulierten Kontext (Jahrgang, Gruppe, Assistent aus dem Editor). Solche Chats stehen
in einer eigenen Liste, werden nach 30 Tagen gelöscht (ADR-011 6.1) und lösen weder
Krisen-Flags noch Zähler aus. `NULL` heißt: ein gewöhnlicher Chat.

**`feedback.preview`** (ADR-020): Die Rückmeldung kam aus der Vorschau. Vorgabe `false`.

**Rücknahme:** `alembic downgrade 0098` entfernt beide Spalten samt Inhalt; Vorschau-Chats
werden dann zu gewöhnlichen Chats.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0099"
down_revision = "0098"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("preview_context", postgresql.JSONB(), nullable=True))
    op.add_column("feedback", sa.Column("preview", sa.Boolean(), nullable=False,
                                        server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("feedback", "preview")
    op.drop_column("conversations", "preview_context")
