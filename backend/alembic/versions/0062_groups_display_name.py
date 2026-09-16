"""`groups.display_name` — ein selbst vergebener Name neben dem aus dem Schulkonto

Die Namen der Unterrichtsgruppen kommen aus dem SSO (`unterricht.ch2-ks-abi28` →
`ch2-ks-abi28`) und sind für die Oberfläche unbrauchbar. Eine Lehrkraft soll ihrer Gruppe
einen lesbaren Namen geben können.

**Warum eine eigene Spalte und nicht `name`.** `sync_groups` setzt `group.name = pg.name`
bei **jedem** Login — der Name ist Eigentum des Schulkontos und muss es bleiben, sonst
bemerkt die Plattform eine Umbenennung dort nicht mehr. Ein in `name` eingetragener
Wunschname wäre nach der nächsten Anmeldung weg.

**Der rohe Name bleibt maßgeblich, wo Maschinen lesen.** Die Stundenplan-Zuordnung sucht
den Klassennamen im Gruppennamen (`_nennt_klasse`) und die Kursart-Marker (`lk`/`bk`) —
beides lebt von der Struktur, die das SSO-Muster liefert. Ein Anzeigename wie „CH Abi28"
hilft dort nichts und nähme der Zuordnung die Klassenangabe. Sie rechnet deshalb weiter
auf `name`; die Zuordnung ist damit gegen Umbenennen immun.

Revision ID: 0062
Revises: 0061
"""
import sqlalchemy as sa
from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("groups", sa.Column("display_name", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("groups", "display_name")
