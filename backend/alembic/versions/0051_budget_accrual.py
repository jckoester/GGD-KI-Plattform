"""budget_accrual: Merkposten der wöchentlichen Zuteilung

Revision ID: 0051
Revises: 0050
Create Date: 2026-08-29 22:00:34.212993

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0051'
down_revision: Union[str, Sequence[str], None] = '0050'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merkposten der wöchentlichen Budget-Zuteilung.

    Das Budget wird seit 08/2026 nicht mehr monatlich zurückgesetzt, sondern je
    Unterrichtswoche aufgestockt. Diese Tabelle hält fest, bis wohin das geschehen ist —
    damit ein wiederholter oder nachgeholter Lauf nicht doppelt bucht.

    Bestandsnutzer brauchen keinen Vorlauf: Wer hier noch keine Zeile hat, bekommt beim
    ersten Lauf die laufende Woche gebucht (kein rückwirkendes Nachholen ab Woche 1).
    """
    op.create_table('budget_accrual',
    sa.Column('pseudonym', sa.String(), nullable=False),
    sa.Column('schuljahr', sa.Text(), nullable=False),
    sa.Column('letzte_woche', sa.Integer(), nullable=False),
    sa.Column('aktualisiert_am', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('pseudonym')
    )


def downgrade() -> None:
    op.drop_table('budget_accrual')
