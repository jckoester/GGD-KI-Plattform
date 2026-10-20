"""Letzte Nachricht bearbeiten und Antwort abbrechen: drei Felder an `messages` (0.19, Schritt 5)

Revision ID: 0088
Revises: 0087
Create Date: 2026-10-20

**`ersetzt_am`** — die Nachricht ist durch eine bearbeitete ersetzt und **ausgeblendet, nicht
gelöscht** (Plan F5, Jan 19.10.2026). Gelöscht ginge mit ihr verloren, was per `ON DELETE
CASCADE` an ihr hängt: die Krisenmeldung (`conversation_flags.message_id`, ADR-008), Bausteine,
Bilder. Der Verlauf für Nutzer:innen lässt sie weg, die Krisen-Einsicht zeigt sie.

**`abgebrochen`** — die Antwort endete vorzeitig (Stopp-Knopf, Tab geschlossen, Netz weg) und
wurde mit dem Teil gespeichert, der bis dahin da war. Bis 0.19 speicherte ein Abbruch gar
nichts, auch nicht die Frage und den Kostenvermerk.

**`werkzeuge_mit_wirkung`** — welche schreibenden Werkzeuge die Antwort ausgeführt hat (etwa
`update_lesson_phases`). Beim Bearbeiten sagt die Oberfläche dann, dass die Änderung bleibt
(Plan F6).

**Rücknahme:** `alembic downgrade 0087` entfernt die Spalten. Ersetzte Nachrichten stehen dann
wieder im Verlauf.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("ersetzt_am", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("messages", sa.Column(
        "abgebrochen", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("messages", sa.Column("werkzeuge_mit_wirkung", ARRAY(sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "werkzeuge_mit_wirkung")
    op.drop_column("messages", "abgebrochen")
    op.drop_column("messages", "ersetzt_am")
