"""site_texts

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


VALID_KEYS = ['impressum', 'datenschutz', 'hilfe', 'regeln']


def upgrade() -> None:
    op.create_table(
        "site_texts",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now()
        ),
    )
    
    # Seed: alle vier Schlüssel mit leerem Inhalt anlegen
    for key in VALID_KEYS:
        op.execute(
            sa.text("INSERT INTO site_texts (key, content) VALUES (:key, '')")
            .bindparams(key=key)
        )


def downgrade() -> None:
    op.drop_table("site_texts")
