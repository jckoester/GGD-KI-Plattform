"""stepup_consumed: Einmalverwendung von Step-up-Token (Sicherheits-Audit #3 Teil C)

Ein Step-up-Token ist an (sub, action, resource_id) gebunden und darf nur einmal
eingelöst werden. Die verbrauchte `jti` wird hier abgelegt; ein Replay im TTL-Fenster
kollidiert am Primärschlüssel und wird abgelehnt.

Revision ID: 0035
Revises: 0034
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stepup_consumed",
        sa.Column("jti", sa.Text(), nullable=False),
        sa.Column("expires_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "consumed_at", postgresql.TIMESTAMP(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("jti"),
    )
    op.create_index("idx_stepup_consumed_expires_at", "stepup_consumed", ["expires_at"])


def downgrade():
    op.drop_index("idx_stepup_consumed_expires_at", table_name="stepup_consumed")
    op.drop_table("stepup_consumed")
