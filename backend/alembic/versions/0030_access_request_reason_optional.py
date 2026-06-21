"""Krisen-Einsicht Phase 12, Schritt 4 (Nachzug): reason optional, Fenster-Default 48h

Der erzwungene Begründungs-Mindesttext erzeugte nur generischen Boilerplate (der
Antragsteller hat außer Trigger/Zeitpunkt/Pseudonym keine Information). Daher wird
reason optional; der Zweck ergibt sich aus dem verknüpften Flag. Default-Zeitfenster
auf 48h (ohne Mail-Benachrichtigung sind 24h zu knapp).

Revision ID: 0030
Revises: 0029
"""

from alembic import op
import sqlalchemy as sa

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "conversation_access_requests",
        "reason",
        existing_type=sa.Text(),
        nullable=True,
    )
    op.alter_column(
        "conversation_access_requests",
        "access_window_hours",
        existing_type=sa.Integer(),
        server_default=sa.text("48"),
    )


def downgrade():
    op.alter_column(
        "conversation_access_requests",
        "access_window_hours",
        existing_type=sa.Integer(),
        server_default=sa.text("24"),
    )
    op.alter_column(
        "conversation_access_requests",
        "reason",
        existing_type=sa.Text(),
        nullable=False,
    )
