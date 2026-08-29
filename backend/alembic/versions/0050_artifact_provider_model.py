"""Modell-Transparenz: artifacts.provider_model

Der Fall mit der Frist. Ein Artefakt überlebt die Konversation bewusst (`origin_conversation_id`
ist nur eine Notiz, kein FK) — die `generated_images`-Zeile stirbt aber per CASCADE mit ihr,
spätestens nach dem 93-Tage-Lifecycle. Ohne diese Spalte ist die Herkunft eines
Bibliotheks-Artefakts danach **unwiederbringlich** weg, und ausgerechnet diese Artefakte
landen in Arbeitsblättern und Facharbeiten.

Gefüllt wird beim Promoten, aus `generated_images.provider_model`. Für Diagramme und
Dokumente bleibt die Spalte vorerst leer: Dort kommt der Inhalt aus einer Chat-Nachricht,
deren Kennung das Frontend gar nicht kennt (die Nachrichten-API liefert keine IDs). Ein vom
Client behaupteter Modellname wäre in einer Quellenangabe das Gegenteil von hilfreich.

Revision ID: 0050
Revises: 0049
"""

from alembic import op
import sqlalchemy as sa

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("artifacts", sa.Column("provider_model", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("artifacts", "provider_model")
