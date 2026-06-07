"""KS-Phase-2: related_to zu context_edges.relation hinzufügen

Revision ID: 0019
Revises: 0018
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE context_edges
        DROP CONSTRAINT check_context_edges_relation,
        ADD CONSTRAINT check_context_edges_relation
            CHECK (relation IN (
                'requires', 'used_with', 'part_of', 'develops',
                'supersedes', 'references', 'follows', 'reflects_on',
                'derived_from', 'related_to'
            ))
    """)


def downgrade():
    op.execute("""
        ALTER TABLE context_edges
        DROP CONSTRAINT check_context_edges_relation,
        ADD CONSTRAINT check_context_edges_relation
            CHECK (relation IN (
                'requires', 'used_with', 'part_of', 'develops',
                'supersedes', 'references', 'follows', 'reflects_on',
                'derived_from'
            ))
    """)
