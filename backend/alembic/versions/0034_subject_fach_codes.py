"""Multi-Fachcode pro Fach: subjects.fach_codes

Manche Fächer haben über die Klassenspanne zwei Bildungspläne mit zwei
Fachcodes (z. B. NwT: NWT für Klasse 8-10, NWTBFO für 11-12). Die skalare
Spalte fach_code trägt weiterhin den Primär-Code (Anzeige/Default); fach_codes
listet ALLE Codes des Fachs, gegen die Cross-Fach-Auflösung und Curriculum-
Erstellung matchen. Geseedet aus config/subjects.yaml (fach_code bzw. fach_codes).

Revision ID: 0034
Revises: 0033
"""

from alembic import op
import sqlalchemy as sa

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "subjects",
        sa.Column(
            "fach_codes",
            sa.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade():
    op.drop_column("subjects", "fach_codes")
