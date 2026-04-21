"""add conversation fields and rename token columns

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-20 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Conversation: neue Felder hinzufügen
    op.add_column('conversations', sa.Column('title', sa.TEXT(), nullable=True))
    op.add_column('conversations', sa.Column('model_used', sa.TEXT(), nullable=False, server_default=''))
    op.add_column('conversations', sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')))
    
    # Message: model Feld hinzufügen
    op.add_column('messages', sa.Column('model', sa.TEXT(), nullable=True))
    
    # Message: input_tokens -> tokens_input, output_tokens -> tokens_output umbenennen
    op.alter_column('messages', 'input_tokens', new_column_name='tokens_input')
    op.alter_column('messages', 'output_tokens', new_column_name='tokens_output')


def downgrade() -> None:
    # Message: Umbenennung rückgängig machen
    op.alter_column('messages', 'tokens_input', new_column_name='input_tokens')
    op.alter_column('messages', 'tokens_output', new_column_name='output_tokens')
    
    # Message: model Feld entfernen
    op.drop_column('messages', 'model')
    
    # Conversation: neue Felder entfernen
    op.drop_column('conversations', 'created_at')
    op.drop_column('conversations', 'model_used')
    op.drop_column('conversations', 'title')
