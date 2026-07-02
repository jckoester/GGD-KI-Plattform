"""generated_images: Referenzen für generierte Bilder (Phase 16)

Die Bild-Bytes liegen auf Disk (app.chat.image_store); diese Tabelle hält nur die
Referenz + Metadaten. FK auf conversations/messages mit ON DELETE CASCADE, damit ein
Bild mit seiner Konversation (bzw. Nachricht) stirbt (93-Tage-Lifecycle). Die
zugehörigen Dateien räumt der Lösch-Pfad bzw. der Aufräum-Cron.

Revision ID: 0035
Revises: 0034
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "generated_images",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("pseudonym", sa.Text(), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("size", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_generated_images_conversation_id", "generated_images", ["conversation_id"]
    )
    op.create_index(
        "idx_generated_images_pseudonym", "generated_images", ["pseudonym"]
    )


def downgrade():
    op.drop_index("idx_generated_images_pseudonym", table_name="generated_images")
    op.drop_index("idx_generated_images_conversation_id", table_name="generated_images")
    op.drop_table("generated_images")
