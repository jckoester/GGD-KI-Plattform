"""Krisen-Einsicht Phase 12, Schritt 8: conversation_flags.resolved_at

Zeitpunkt der Resolution (Flag → resolved/dismissed) als Grundlage der 180-Tage-
Aufbewahrung geflaggter Konversationen im Cleanup-Cron (ADR-008 Teil 7).

Revision ID: 0031
Revises: 0030
"""

from alembic import op
import sqlalchemy as sa

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "conversation_flags",
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("conversation_flags", "resolved_at")
