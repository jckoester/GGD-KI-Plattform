"""Tabelle `budget_grants`: von Hand aufgebuchte Zuschläge (0.12, Paket 2, AP1)

Revision ID: 0081
Revises: 0080
Create Date: 2026-10-02

Ein Zuschlag kommt **obendrauf**, statt die Wochenaufstockung einzufrieren. Bis jetzt
ließ sich Budget nur über `max_budget` am Proxy erhöhen — und das liegt über dem Deckel
der Aufstockung (`verbrauch + vorsprung × wochenbetrag`), friert sie also ein, bis der
Verbrauch aufholt. Gemessen: sieben Wochen ohne Zuwachs. Die Summe der Zeilen dieser
Tabelle hebt den Deckel mit an.

Append-only, je Mitglied eine Zeile, gilt für ein Schuljahr. Die Begründung steht am
Modell (`app/db/models.py`, `BudgetGrant`).

**Rücknahme:** `alembic downgrade 0080` entfernt die Tabelle samt Inhalt. Bereits am
Proxy angehobene Grenzen bleiben stehen — sie werden ab der nächsten Aufstockung wieder
vom Deckel eingeholt, sinken aber nie (die Aufstockung kürzt nicht).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "budget_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pseudonym", sa.Text(), nullable=False),
        sa.Column("schuljahr", sa.Text(), nullable=False),
        sa.Column("betrag_usd", sa.Float(), nullable=False),
        sa.Column("grund", sa.Text(), nullable=False),
        sa.Column("erstellt_von", sa.Text(), nullable=False),
        sa.Column(
            "erstellt_am", TIMESTAMP(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "quelle_gruppe_id", sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.CheckConstraint("betrag_usd > 0", name="check_budget_grants_positiv"),
    )
    op.create_index("ix_budget_grants_pseudonym", "budget_grants", ["pseudonym"])
    op.create_index(
        "ix_budget_grants_pseudonym_schuljahr", "budget_grants", ["pseudonym", "schuljahr"]
    )


def downgrade() -> None:
    op.drop_index("ix_budget_grants_pseudonym_schuljahr", table_name="budget_grants")
    op.drop_index("ix_budget_grants_pseudonym", table_name="budget_grants")
    op.drop_table("budget_grants")
