"""calendar_sources — externe Stundenplan-/Kalenderquellen (UP-8, Schritt 1)

Eine Zeile je eingerichteter Quelle. Beim WebUntis-Weg genügt **eine** schulweite Zeile
(`pseudonym IS NULL`); die Spalte `pseudonym` existiert für den ICS-Rückfallweg, bei dem
jede Lehrkraft ihre eigene Abo-URL hätte.

`config` hält die Verbindungsparameter als JSONB. Zugangsdaten stehen darin
**verschlüsselt** (`app/calendar/secrets.py`) — die Spalte landet in jedem Backup und
jedem Dump. `last_error` ist die Kurzfassung für die Statusanzeige und darf aus demselben
Grund nie Zugangsdaten enthalten.

Zwei partielle Unique-Indizes statt einer Bedingung: In PostgreSQL sind NULL-Werte in
einem Unique-Index untereinander verschieden, ein einfaches UNIQUE(kind, pseudonym) würde
also beliebig viele schulweite Quellen derselben Art zulassen. Genau die dürfen aber nicht
doppelt sein — zwei aktive Quellen würden einander überschreiben, ohne dass jemand sähe,
welche gewonnen hat.

Revision ID: 0044
Revises: 0043
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pseudonym", sa.Text(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("adapter", sa.Text(), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("last_sync_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_status", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
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
        sa.CheckConstraint(
            "kind IN ('stundenplan','vertretung','ferien')", name="check_cs_kind"
        ),
        sa.CheckConstraint(
            "last_status IS NULL OR last_status IN "
            "('ok','auth_failed','parse_failed','empty','no_school_year')",
            name="check_cs_last_status",
        ),
    )
    op.create_index(
        "uq_calendar_sources_kind_owner",
        "calendar_sources",
        ["kind", "pseudonym"],
        unique=True,
        postgresql_where=sa.text("pseudonym IS NOT NULL"),
    )
    op.create_index(
        "uq_calendar_sources_kind_schoolwide",
        "calendar_sources",
        ["kind"],
        unique=True,
        postgresql_where=sa.text("pseudonym IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_calendar_sources_kind_schoolwide", table_name="calendar_sources")
    op.drop_index("uq_calendar_sources_kind_owner", table_name="calendar_sources")
    op.drop_table("calendar_sources")
