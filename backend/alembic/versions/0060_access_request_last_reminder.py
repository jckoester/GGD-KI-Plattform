"""`conversation_access_requests.last_reminder_at` — wann zuletzt an den Antrag erinnert wurde.

Dieselbe Aufgabe wie `0059` bei den Flags, für die andere Hälfte des Krisenprozesses:
Der tägliche Lauf soll nicht täglich dieselbe Mahnung schicken.

**Warum es hier eine eigene Spalte braucht und nicht die des Flags genügt.** Ein Antrag
hängt zwar an einem Flag, aber die beiden Erinnerungen gehen an **verschiedene
Postfächer**: die Flag-Erinnerung an die Krisen-Zuständigen, die Antrags-Erinnerung an
die `review`-Personen, die zweitfreigeben. Das Vier-Augen-Prinzip lebt davon, dass das
nicht dieselben Leute sind (ADR-008 Teil 6) — also haben beide auch ihren eigenen
Rhythmus.

**Keine zweite Löschfrist.** Anders als bei `conversation_flags` steuert diese Spalte
*nur* die Erinnerung. Ein Antrag hat keine Aufbewahrungsgrenze: Er verfällt mit seinem
Flag (`ondelete="CASCADE"`), und dessen Grenze regelt bereits `0059`.

`NULL` heißt „noch nie erinnert" — der Zustand aller Bestandszeilen.

Revision ID: 0060
Revises: 0059
"""
from alembic import op
import sqlalchemy as sa

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_access_requests",
        sa.Column("last_reminder_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    # Teilindex auf die wartenden Anträge — genau danach fragt der tägliche Lauf.
    # `idx_access_requests_status` gibt es zwar schon, aber der deckt alle fünf Stati
    # ab; gefragt wird immer nur nach einem, sortiert nach Alter.
    op.create_index(
        "idx_access_requests_pending_requested_at",
        "conversation_access_requests",
        ["requested_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "idx_access_requests_pending_requested_at",
        table_name="conversation_access_requests",
    )
    op.drop_column("conversation_access_requests", "last_reminder_at")
