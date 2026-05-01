"""assistants: vollstaendiges Schema (Phase 2 Schritt 3a)

Revision ID: 0009
Revises: 0008
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    # Pflichtfelder (NOT NULL, leerer server_default fuer die Migration)
    op.add_column("assistants", sa.Column("name", sa.Text(), nullable=False, server_default="''"))
    op.add_column("assistants", sa.Column("system_prompt", sa.Text(), nullable=False, server_default="''"))
    op.add_column("assistants", sa.Column("model", sa.Text(), nullable=False, server_default="''"))

    # Optionale Config-Felder
    op.add_column("assistants", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("assistants", sa.Column("temperature", sa.Numeric(3, 2), nullable=True))
    op.add_column("assistants", sa.Column("max_tokens", sa.Integer(), nullable=True))

    # Sichtbarkeitsmodell
    op.add_column("assistants", sa.Column(
        "audience", sa.Text(), nullable=False, server_default="'student'"))
    op.add_column("assistants", sa.Column(
        "scope", sa.Text(), nullable=False, server_default="'private'"))
    op.add_column("assistants", sa.Column(
        "scope_pending", sa.Text(), nullable=True))
    op.add_column("assistants", sa.Column(
        "scope_group_id", sa.Integer(), nullable=True))

    # Jahrgangseingrenzung
    op.add_column("assistants", sa.Column("min_grade", sa.Integer(), nullable=True))
    op.add_column("assistants", sa.Column("max_grade", sa.Integer(), nullable=True))

    # UI / Marktplatz
    op.add_column("assistants", sa.Column(
        "tags", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("assistants", sa.Column("icon", sa.Text(), nullable=True))
    op.add_column("assistants", sa.Column("import_metadata", postgresql.JSONB(), nullable=True))

    # Sortierung & Audit
    op.add_column("assistants", sa.Column(
        "sort_order", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("assistants", sa.Column(
        "created_at", postgresql.TIMESTAMP(timezone=True),
        nullable=False, server_default=sa.text("now()")))
    op.add_column("assistants", sa.Column(
        "updated_at", postgresql.TIMESTAMP(timezone=True),
        nullable=False, server_default=sa.text("now()")))
    op.add_column("assistants", sa.Column("updated_by_pseudonym", sa.Text(), nullable=True))

    # Zeitfenster (optional; NULL = sofort / unbegrenzt)
    op.add_column("assistants", sa.Column(
        "available_from",  postgresql.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("assistants", sa.Column(
        "available_until", postgresql.TIMESTAMP(timezone=True), nullable=True))

    # CHECK-Constraints
    op.create_check_constraint(
        "check_assistant_audience",
        "assistants",
        "audience IN ('student', 'teacher', 'all')",
    )
    op.create_check_constraint(
        "check_assistant_scope",
        "assistants",
        "scope IN ('private', 'subject_department', 'teachers', 'activity_group', "
        "          'class_group', 'grade', 'all_students', 'all')",
    )
    op.create_check_constraint(
        "check_assistant_scope_pending",
        "assistants",
        "scope_pending IS NULL OR scope_pending IN "
        "('private', 'subject_department', 'teachers', 'activity_group', "
        " 'class_group', 'grade', 'all_students', 'all')",
    )

    # Indizes fuer haeufige Abfragen
    op.create_index("idx_assistants_status", "assistants", ["status"])
    op.create_index("idx_assistants_subject_id", "assistants", ["subject_id"])


def downgrade():
    op.drop_index("idx_assistants_subject_id")
    op.drop_index("idx_assistants_status")
    op.drop_constraint("check_assistant_scope_pending", "assistants")
    op.drop_constraint("check_assistant_scope", "assistants")
    op.drop_constraint("check_assistant_audience", "assistants")
    for col in [
        "available_until", "available_from",
        "updated_by_pseudonym", "updated_at", "created_at", "sort_order",
        "import_metadata", "icon", "tags",
        "max_grade", "min_grade",
        "scope_group_id", "scope_pending", "scope", "audience",
        "max_tokens", "temperature", "description", "model", "system_prompt", "name",
    ]:
        op.drop_column("assistants", col)
