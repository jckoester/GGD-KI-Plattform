"""add groups and group_memberships tables

Revision ID: 0012
Revises: 0011
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0012'
down_revision: Union[str, None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- 1. groups --
    op.create_table(
        'groups',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('slug', sa.Text(), nullable=False),
        sa.Column('type', sa.Text(), nullable=False),
        sa.Column('subject_id', sa.Integer(),
                  sa.ForeignKey('subjects.id', ondelete='SET NULL'), nullable=True),
        sa.Column('sso_group_id', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('slug', name='uq_groups_slug'),
        sa.CheckConstraint(
            "type IN ('school_class','subject_department','teaching_group','activity_group','teachers')",
            name='check_groups_type',
        ),
    )
    op.create_index('idx_groups_type', 'groups', ['type'])
    op.create_index('idx_groups_subject_id', 'groups', ['subject_id'])

    # -- 2. group_memberships --
    op.create_table(
        'group_memberships',
        sa.Column('group_id', sa.Integer(),
                  sa.ForeignKey('groups.id', ondelete='CASCADE'), nullable=False),
        sa.Column('pseudonym', sa.Text(), nullable=False),
        sa.Column('role_in_group', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('group_id', 'pseudonym', name='pk_group_memberships'),
        sa.CheckConstraint(
            "role_in_group IS NULL OR role_in_group IN ('teacher','student')",
            name='check_group_memberships_role',
        ),
    )
    op.create_index('idx_group_memberships_pseudonym', 'group_memberships', ['pseudonym'])

    # -- 3. FK: assistants.scope_group_id -> groups(id) --
    op.create_foreign_key(
        'fk_assistants_scope_group_id',
        'assistants', 'groups',
        ['scope_group_id'], ['id'],
        ondelete='SET NULL',
    )

    # -- 4. Umbenennung class_group -> teaching_group in assistants.scope --
    # Kein Datenverlust: class_group war per Validierung blockiert, existiert nicht in DB.
    op.drop_constraint('check_assistant_scope', 'assistants', type_='check')
    op.create_check_constraint(
        'check_assistant_scope',
        'assistants',
        "scope IN ('private','subject_department','teachers','activity_group','teaching_group','grade','all_students','all')",
    )
    op.drop_constraint('check_assistant_scope_pending', 'assistants', type_='check')
    op.create_check_constraint(
        'check_assistant_scope_pending',
        'assistants',
        "scope_pending IS NULL OR scope_pending IN ('private','subject_department','teachers','activity_group','teaching_group','grade','all_students','all')",
    )


def downgrade() -> None:
    # CHECK constraints zuruecksetzen
    op.drop_constraint('check_assistant_scope_pending', 'assistants', type_='check')
    op.create_check_constraint(
        'check_assistant_scope_pending',
        'assistants',
        "scope_pending IS NULL OR scope_pending IN ('private','subject_department','teachers','activity_group','class_group','grade','all_students','all')",
    )
    op.drop_constraint('check_assistant_scope', 'assistants', type_='check')
    op.create_check_constraint(
        'check_assistant_scope',
        'assistants',
        "scope IN ('private','subject_department','teachers','activity_group','class_group','grade','all_students','all')",
    )
    # FK entfernen
    op.drop_constraint('fk_assistants_scope_group_id', 'assistants', type_='foreignkey')
    # Tabellen entfernen
    op.drop_table('group_memberships')
    op.drop_table('groups')
