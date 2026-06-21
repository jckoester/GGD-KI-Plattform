"""Krisen-Einsicht Phase 12, Schritt 4: access_window_hours am Einsicht-Antrag

Beim Antrag gewünschte Fensterdauer (Stunden); wird bei der Zweitfreigabe (Schritt 6)
zu access_granted_until = Freigabe-Zeitpunkt + access_window_hours.

Revision ID: 0029
Revises: 0028
"""

from alembic import op
import sqlalchemy as sa

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "conversation_access_requests",
        sa.Column(
            "access_window_hours",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("24"),
        ),
    )
    op.create_check_constraint(
        "check_access_request_window_hours",
        "conversation_access_requests",
        "access_window_hours BETWEEN 1 AND 168",
    )


def downgrade():
    op.drop_constraint(
        "check_access_request_window_hours",
        "conversation_access_requests",
        type_="check",
    )
    op.drop_column("conversation_access_requests", "access_window_hours")
