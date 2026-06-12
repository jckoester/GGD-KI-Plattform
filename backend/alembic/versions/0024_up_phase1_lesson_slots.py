"""UP-Phase-1: lesson_slots, slot_plan_snapshots, group_week_patterns

Revision ID: 0024
Revises: 0023
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "group_week_patterns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("halbjahr", sa.Integer(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_period", sa.Integer(), nullable=False),
        sa.Column("periods", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("halbjahr IN (1, 2)", name="check_gwp_halbjahr"),
        sa.CheckConstraint("weekday BETWEEN 0 AND 4", name="check_gwp_weekday"),
        sa.CheckConstraint("periods IN (1, 2)", name="check_gwp_periods"),
    )
    op.create_index(
        "idx_gwp_unique",
        "group_week_patterns",
        ["group_id", "halbjahr", "weekday", "start_period"],
        unique=True,
    )

    op.create_table(
        "lesson_slots",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("start_period", sa.Integer(), nullable=True),
        sa.Column("periods", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("halbjahr", sa.Integer(), nullable=False),
        sa.Column(
            "kategorie",
            sa.Text(),
            nullable=False,
            server_default="unterricht",
        ),
        sa.Column(
            "ue_node_id",
            sa.UUID(),
            sa.ForeignKey("context_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "stunde_node_id",
            sa.UUID(),
            sa.ForeignKey("context_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("thema", sa.Text(), nullable=True),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "anpassung_noetig", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "nachbereitet_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "nachbereitet_auto",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("halbjahr IN (1, 2)", name="check_ls_halbjahr"),
        sa.CheckConstraint(
            "kategorie IN ('unterricht','pruefung','ausfall','puffer','vertretung')",
            name="check_ls_kategorie",
        ),
    )
    op.create_index(
        "idx_lesson_slots_group_date",
        "lesson_slots",
        ["group_id", "date"],
    )

    op.create_table(
        "slot_plan_snapshots",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "reason IN ('manual','edit','swap','regeneration','restore','assistant','reflow')",
            name="check_sps_reason",
        ),
    )
    op.create_index(
        "idx_slot_snapshots_group",
        "slot_plan_snapshots",
        ["group_id", "created_at"],
    )


def downgrade():
    op.drop_index("idx_slot_snapshots_group", table_name="slot_plan_snapshots")
    op.drop_table("slot_plan_snapshots")

    op.drop_index("idx_lesson_slots_group_date", table_name="lesson_slots")
    op.drop_table("lesson_slots")

    op.drop_index("idx_gwp_unique", table_name="group_week_patterns")
    op.drop_table("group_week_patterns")
