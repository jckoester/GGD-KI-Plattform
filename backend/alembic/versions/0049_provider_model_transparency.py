"""Modell-Transparenz: messages.provider_model, generated_images.provider_model

Bisher stand in `model` nur der schulinterne Aliasname (`chat-standard`) — für eine
Quellenangabe in GFS, Seminarkurs oder Facharbeit wertlos. Zitierfähig ist das
Anbietermodell (`openai/openai/gpt-oss-120b`).

Beide Spalten stehen **neben** dem Alias, sie ersetzen ihn nicht: Der Alias sagt, welche
Aufgabe gemeint war, das Anbietermodell, was tatsächlich geantwortet hat. Für Betrieb und
Statistik ist der Alias die nützlichere Angabe.

Nullable und ohne Backfill: Für Bestandszeilen ist das Anbietermodell nicht rekonstruierbar
— welcher Alias damals auf welches Modell zeigte, weiß niemand mehr. Ein geratener Wert
wäre schlimmer als eine Leerstelle, gerade bei einer Quellenangabe.

Revision ID: 0049
Revises: 0048
"""

from alembic import op
import sqlalchemy as sa

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("messages", sa.Column("provider_model", sa.Text(), nullable=True))
    op.add_column("generated_images", sa.Column("provider_model", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("generated_images", "provider_model")
    op.drop_column("messages", "provider_model")
