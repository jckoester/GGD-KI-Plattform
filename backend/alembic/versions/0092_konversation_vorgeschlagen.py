"""Konversation: schon vorgeschlagene Assistenten (Päckchen C2, Schritt 3)

Revision ID: 0092
Revises: 0091
Create Date: 2026-10-28

**`conversations.vorgeschlagen`** (Liste von Assistenten-IDs, Vorgabe leer): die Ruheregel des
Vorschlags im Chat (Plan C2, F4). Jeder Assistent wird je Konversation höchstens einmal
angeboten; 0 steht für „Assistent beenden". Ein angenommener Wechsel leert die Liste.

Keine personenbezogenen Daten: nur Kennungen von Assistenten, und die Liste lebt und stirbt mit
der Konversation (Löschfrist 93 Tage).

**Rücknahme:** `alembic downgrade 0091` entfernt die Spalte.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0092"
down_revision = "0091"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("vorgeschlagen", postgresql.ARRAY(sa.Integer()), nullable=False,
                  server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("conversations", "vorgeschlagen")
