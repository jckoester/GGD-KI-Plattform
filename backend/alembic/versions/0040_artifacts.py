"""artifacts: persönliche Artefaktbibliothek (Phase 18)

Persistente, konversationsübergreifende Artefakte (Bilder, gerenderte Diagramme, ggb …).
Bytes liegen auf Disk (app.artifacts.store); diese Tabelle hält Referenz + Metadaten.
`origin_conversation_id` ist nur Herkunfts-Notiz (KEIN FK/CASCADE — das Artefakt überlebt die
Konversation). `expires_at` = role-/jahrgangsbasierte Aufbewahrung, beim Speichern eingefroren.

Revision ID: 0040
Revises: 0039
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "artifacts",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("owner_pseudonym", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("origin_conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_artifacts_owner", "artifacts", ["owner_pseudonym"])
    op.create_index("idx_artifacts_expires_at", "artifacts", ["expires_at"])


def downgrade():
    op.drop_index("idx_artifacts_expires_at", table_name="artifacts")
    op.drop_index("idx_artifacts_owner", table_name="artifacts")
    op.drop_table("artifacts")
