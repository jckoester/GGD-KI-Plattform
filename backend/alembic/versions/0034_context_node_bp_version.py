"""context_nodes.bp_version: Bildungsplan-Edition als eigenes Feld

Macht die Edition ("" = Basis/V1, ".V2", ".V3" …) explizit abfragbar, statt
sie nur implizit im bp_id-String zu führen. Grundlage für die
schuljahresabhängige Editionsauswahl (Versionierungs-Phase). Backfill aus dem
Fach-Segment des bp_id (z. B. "BP2016BW_ALLG_GYM_CH.V2_IK_…" → ".V2").

Revision ID: 0034
Revises: 0033
"""

from alembic import op
import sqlalchemy as sa

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "context_nodes",
        sa.Column(
            "bp_version",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )
    # Backfill aus dem bp_id — identisch zum Scraper-Feld `bp_version`
    # (Basisjahr + Editions-Suffix): Jahr aus dem "BP<jahr>"-Präfix, Suffix aus
    # dem 4. '_'-Segment.
    #   "BP2016BW_ALLG_GYM_CH.V2_IK_…" → "2016" || ".V2" = "2016.V2"
    #   "BP2016BW_ALLG_GYM_M_IK_…"     → "2016" || ""    = "2016"
    # Knoten ohne BP-Jahr (kurze LP-Codes wie "BO_01") bleiben "".
    op.execute(
        r"""
        UPDATE context_nodes
        SET bp_version =
            COALESCE(substring(metadata->>'bp_id' FROM 'BP(\d{4})'), '') ||
            COALESCE(substring(split_part(metadata->>'bp_id', '_', 4) FROM '\.[A-Za-z0-9.]+$'), '')
        WHERE metadata->>'bp_id' IS NOT NULL
        """
    )


def downgrade():
    op.drop_column("context_nodes", "bp_version")
