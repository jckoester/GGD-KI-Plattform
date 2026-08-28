"""Mehrmodell-Bildgenerierung: generated_images.bildart

Die Bildart-ID, mit der ein Bild erzeugt wurde. Zwei Zwecke:

* **Anzeige** — Lehrkräfte sollen sehen, welche Bildart gegriffen hat; nur so lässt sich
  beurteilen, ob das Routing bei mehreren Bildarten sinnvoll wählt.
* **Variieren** — der zweite Versuch soll dieselbe Bildart nehmen, nicht die Standard-.

Nullable: Bilder aus der Zeit davor haben keine, und aus Modell + Größe ließe sie sich
nicht eindeutig rekonstruieren (zwei Bildarten dürfen dasselbe Modell nutzen). Für die
Anzeige heißt das schlicht: nichts zeigen.

Revision ID: 0048
Revises: 0047
"""

from alembic import op
import sqlalchemy as sa

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("generated_images", sa.Column("bildart", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("generated_images", "bildart")
