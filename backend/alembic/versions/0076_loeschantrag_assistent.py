"""Löschantrag für schulweite Assistenten — als Feld, nicht als Status

Revision ID: 0076
Revises: 0075
Create Date: 2026-09-25

⚠️ **Warum kein Status.** `assistants.status` beantwortet genau **eine** Frage: Ist
dieser Assistent benutzbar, und von wem? Die Chat-Liste filtert darüber
(`app/api/assistants.py`, `status == "active"`); an der Spalte hängen 25 Stellen im
Backend und rund sechs Status-Tabellen im Frontend.

Ein Löschantrag soll den Assistenten **nicht** abschalten (Entscheidung Jan,
25.09.2026): Er bleibt im Unterricht, bis der Admin entscheidet. Ein Statuswert
`deletion_requested` müsste deshalb überall wie `active` behandelt werden — zwei Werte
mit derselben Bedeutung, also genau die Unklarheit, gegen die es eine Statusspalte gibt.
Eine Markierung **neben** dem Status sagt dasselbe, ohne das zu zerstören.

**Nur für den schulweiten Zweig.** Eigene Gruppen- und Fachschafts-Assistenten löscht
die Lehrkraft selbst; dort gibt es nichts zu beantragen.

**Kein Backfill**: Vor heute hat niemand einen Antrag gestellt.
"""
import sqlalchemy as sa
from alembic import op

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assistants",
        sa.Column("deletion_requested_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column("assistants", sa.Column("deletion_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("assistants", "deletion_reason")
    op.drop_column("assistants", "deletion_requested_at")
