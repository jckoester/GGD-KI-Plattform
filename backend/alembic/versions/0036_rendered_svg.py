"""rendered_svg: Cache für server-gerenderte SVGs (Phase 17)

Content-adressierter Cache (Hash der Render-Quelle → SVG). Rein deterministische
Funktion, konversations-/nutzerunabhängig; altersbasiert aufgeräumt
(app.render.cache.cleanup_rendered_svg). Index auf created_at für den Aufräum-Cron.

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
    op.create_table(
        "rendered_svg",
        sa.Column("hash", sa.Text(), nullable=False),
        sa.Column("svg", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("hash"),
    )
    op.create_index("idx_rendered_svg_created_at", "rendered_svg", ["created_at"])


def downgrade():
    op.drop_index("idx_rendered_svg_created_at", table_name="rendered_svg")
    op.drop_table("rendered_svg")
