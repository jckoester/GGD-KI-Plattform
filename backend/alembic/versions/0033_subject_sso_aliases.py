"""Fach-SSO-Aliase: subjects.sso_aliases

Alternative SSO-Gruppennamen pro Fach (z. B. fs.bildende.kunst → kunst,
fs.religion.ev → religion-ev), geseedet aus config/subjects.yaml.
Ersetzt den sso.subject_aliases-Block in auth.yaml — Single Source of
Truth für alle Fach-Einstellungen ist damit subjects.yaml.

Revision ID: 0033
Revises: 0032
"""

from alembic import op
import sqlalchemy as sa

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "subjects",
        sa.Column(
            "sso_aliases",
            sa.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade():
    op.drop_column("subjects", "sso_aliases")
