"""pseudonym_audit.roles: voller Rollensatz für Auto-Session-Revocation (Sicherheits-Audit #11)

Bisher speichert `pseudonym_audit.role` nur die Primärrolle (teacher>student); additive
Rollen (admin/review) fehlen. Für die automatische Session-Revocation bei Rollen-Schrumpfung
(E) wird der volle Rollensatz benötigt. Nullable — wird beim ersten Login nach dem Rollout
gefüllt; bis dahin gibt es keine Baseline und E greift für den betreffenden Nutzer erst ab
dem zweiten Login.

Revision ID: 0036
Revises: 0035
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "pseudonym_audit",
        sa.Column("roles", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade():
    op.drop_column("pseudonym_audit", "roles")
