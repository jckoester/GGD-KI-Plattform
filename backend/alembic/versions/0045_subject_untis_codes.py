"""Fach-Kürzel des Stundenplans: subjects.untis_codes (UP-8, Schritt 7)

Die Fachkürzel, unter denen WebUntis ein Fach führt — geseedet aus `config/subjects.yaml`.

**Warum ein eigenes Feld und nicht `sso_aliases` oder `fach_code`?** Weil es ein drittes
Vokabular ist. Der Abgleich am 06.08.2026 zeigte: Von elf beobachteten Stundenplan-Kürzeln
löste sich genau eines über Slug/Alias auf und zwei über `fach_code`.

    Bildungsplan (fach_code):  ETH   INFWFO   M   GEO
    Stundenplan (untis_codes): ET    INF      M   GEO

`ETH` ≠ `ET`, `INFWFO` ≠ `INF` — die Kürzel ähneln einander gerade genug, um die
Verwechslung nahezulegen, und weichen gerade so weit ab, dass ein Abgleich scheitert. Sie
in `sso_aliases` zu mischen hieße, zwei Vokabulare in ein Feld zu legen, das als
„alternative SSO-Gruppennamen" dokumentiert ist; ein Kürzel wie `sl` könnte dort mit einem
Gruppennamen kollidieren.

Mehrere Kürzel je Fach sind üblich (Differenzierung, Profilfächer), deshalb eine Liste.

Revision ID: 0045
Revises: 0044
"""
from alembic import op
import sqlalchemy as sa

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subjects",
        sa.Column(
            "untis_codes",
            sa.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("subjects", "untis_codes")
