"""Assistenten: Auslöser-Beispiele und Vorschlagsfelder (Päckchen C1, Schritt 3)

Revision ID: 0090
Revises: 0089
Create Date: 2026-10-25

**`assistant_trigger_examples`** hält je Assistent typische erste Schülernachrichten, für die
er passt (`art = 'beispiel'`), und solche, die nicht zu ihm gehören (`'gegenbeispiel'`, F4 b,
Jan 25.10.2026) — beide mit Embedding. C2 vergleicht die Chatnachricht damit.

⚠️ **Vektor ohne feste Breite, dazu `embedding_model`.** `context_nodes.embedding` trägt die
Breite im Typ, und ein Modellwechsel stellt sie mit `scripts/resize_embedding_column.py` um.
Hier entfällt das: Ein Vektor gilt nur, wenn `embedding_model` dem eingestellten Modell
entspricht; sonst bettet der nächtliche Lauf neu ein. So bleibt der Modellwechsel ein Schritt
für eine Tabelle.

**Am Assistenten** (F5): `suggest` (`specific` | `fallback` | `never`, Vorgabe `never` — ohne
Beispiele schlägt ohnehin nichts vor), `suggestion_text` (der Satz im Dialog) und `fallbacks`
(IDs allgemeiner Assistenten, die unter einem spezifischen Treffer erscheinen).

**Rücknahme:** `alembic downgrade 0089` entfernt Tabelle und Spalten samt Inhalt.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0090"
down_revision = "0089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assistants",
        sa.Column("suggest", sa.Text(), nullable=False, server_default=sa.text("'never'")),
    )
    op.create_check_constraint(
        "check_assistant_suggest", "assistants",
        "suggest IN ('specific', 'fallback', 'never')",
    )
    op.add_column("assistants", sa.Column("suggestion_text", sa.Text(), nullable=True))
    op.add_column(
        "assistants",
        sa.Column(
            "fallbacks", postgresql.ARRAY(sa.Integer()), nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )

    op.create_table(
        "assistant_trigger_examples",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "assistant_id", sa.Integer(),
            sa.ForeignKey("assistants.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("art", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "art IN ('beispiel', 'gegenbeispiel')", name="check_trigger_example_art"
        ),
        sa.UniqueConstraint("assistant_id", "art", "text", name="uq_trigger_example_text"),
    )
    # pgvector ohne Breitenangabe — siehe Modulkopf.
    op.execute("ALTER TABLE assistant_trigger_examples ADD COLUMN embedding vector")
    op.create_index(
        "ix_trigger_examples_assistant", "assistant_trigger_examples", ["assistant_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_trigger_examples_assistant", table_name="assistant_trigger_examples")
    op.drop_table("assistant_trigger_examples")
    op.drop_column("assistants", "fallbacks")
    op.drop_column("assistants", "suggestion_text")
    op.drop_constraint("check_assistant_suggest", "assistants", type_="check")
    op.drop_column("assistants", "suggest")
