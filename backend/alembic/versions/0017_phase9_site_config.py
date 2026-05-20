"""Phase 9 Schritt 1: site_config ersetzt site_texts

Revision ID: 0017
Revises: 0016
"""

from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

SITE_TEXT_KEYS = ["impressum", "datenschutz", "hilfe", "regeln"]


def upgrade():
    op.create_table(
        "site_config",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_by", sa.Text(), nullable=True),
    )

    # Vorhandene site_texts-Einträge übernehmen
    op.execute(sa.text("""
        INSERT INTO site_config (key, value, updated_at, updated_by)
        SELECT key, NULLIF(content, ''), updated_at, NULL
        FROM site_texts
    """))

    op.drop_table("site_texts")


def downgrade():
    op.create_table(
        "site_texts",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Einträge zurückschreiben (nur die vier Seed-Keys)
    for key in SITE_TEXT_KEYS:
        op.execute(
            sa.text(
                "INSERT INTO site_texts (key, content)"
                " SELECT key, COALESCE(value, '') FROM site_config WHERE key = :key"
            ).bindparams(key=key)
        )

    op.drop_table("site_config")
