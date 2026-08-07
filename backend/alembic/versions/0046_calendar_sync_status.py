"""calendar_sync_status — Ergebnis des Stundenplan-Abgleichs (UP-8, Schritt 10a)

Eine Zeile je Lehrkraft: wann zuletzt abgeglichen, mit welchem Ergebnis, wie viel geändert.

**Warum überhaupt eine Tabelle?** Bei Schritt 1 wurde `calendar_sources` verworfen, weil
Zugangsdaten in die Umgebung gehören — ein schulweites Geheimnis braucht keine Datenbank.
Der **Abrufstatus** ist aber veränderlicher Laufzeitzustand und lässt sich nicht in eine
`.env` schreiben. Die Form ergibt sich aus dem, was die Anzeige zeigt: Zeitpunkt, Ergebnis,
Umfang — mehr nicht.

**Schlüssel ist das Pseudonym**, nicht das WebUntis-Kürzel: Der Status gehört zu einem
Konto der Plattform, nicht zu einer Person im Stundenplan. Wer sein Kürzel wechselt, behält
seinen Status; wer das Konto verliert, verliert ihn mit (`ON DELETE` gibt es hier nicht,
der Löschpfad in Schritt 11 räumt auf).

Revision ID: 0046
Revises: 0045
"""
from alembic import op
import sqlalchemy as sa

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_sync_status",
        sa.Column("pseudonym", sa.Text(), primary_key=True),
        sa.Column("last_sync_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        # Kurzfassung für die Anzeige — **ohne** Zugangsdaten. Die Meldungen stammen aus
        # `CalendarSourceError`, die Adapter selbst formulieren (siehe app/calendar/base.py).
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("changed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("conflicts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("shifts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('ok','kein_kuerzel','quelle_fehlt','nicht_erreichbar',"
            "'anmeldung_fehlgeschlagen','fehler')",
            name="check_css_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("calendar_sync_status")
