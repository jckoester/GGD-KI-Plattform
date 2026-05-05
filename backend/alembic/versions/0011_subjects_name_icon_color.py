"""add name, icon, color to subjects

Revision ID: 0011
Revises: 0010
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0011'
down_revision: Union[str, None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Spalten ergänzen (zunächst nullable, damit bestehende Zeilen erlaubt sind)
    op.add_column('subjects', sa.Column('name', sa.Text(), nullable=True))
    op.add_column('subjects', sa.Column('icon', sa.Text(), nullable=True))
    op.add_column('subjects', sa.Column('color', sa.Text(), nullable=True))

    # Vorhandene Zeilen befüllen (initcap(slug) als Fallback)
    op.execute("UPDATE subjects SET name = initcap(slug) WHERE name IS NULL")

    # Jetzt NOT NULL setzen
    op.alter_column('subjects', 'name', nullable=False)


def downgrade() -> None:
    op.drop_column('subjects', 'color')
    op.drop_column('subjects', 'icon')
    op.drop_column('subjects', 'name')
