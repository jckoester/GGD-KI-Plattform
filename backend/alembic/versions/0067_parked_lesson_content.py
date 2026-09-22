"""`parked_lesson_content` — Planungsinhalt, der gerade keinen Termin hat

Ändert sich das Wochenmuster, wird die Jahresplanung auf das neue Raster **umgehängt**:
Inhalt wandert nach Reihenfolge auf die neuen Termine. Hat das neue Raster weniger
Termine als die alte Planung Inhalte, bleibt etwas übrig. Dieser Rest landet hier —
nicht im Papierkorb.

**Warum ein eigener Ort und nicht „auf dem letzten Termin stapeln".** Slot und Inhalt
stehen 1:1 (`lesson_slots.ue_node_id`, `stunde_node_id`, `thema` sind Einzelspalten).
Stapeln bräuchte deshalb dieselbe Modelländerung wie dieser Parkplatz, versteckte das
Problem aber an der schädlichsten Stelle: Die letzte Stunde des Halbjahres trüge
stillschweigend drei Stunden Inhalt. Und der eigentliche Lösungsweg — kürzen oder
umplanen — hätte an einem Stapel keinen Griff, weil die überzähligen Stunden kein
eigenes Ding wären.

**`herkunft_datum` ist Sortierschlüssel und Auskunft zugleich:** „war für den 12.03.
geplant". Ohne die Angabe stünde auf dem Parkplatz eine Liste ohne Zusammenhang.

**Kein Pseudonym.** Der Eintrag hängt an der Gruppe, nicht an einer Person — wie die
Slots selbst. ⚠️ Damit meldet `test_pseudonym_deletion_coverage` diese Tabelle **nicht**;
aufgeräumt wird sie über die Cascade der Gruppe.

**Zu den beiden Fremdschlüsseln.** `stunde_node_id` löscht mit (`CASCADE`): Der Eintrag
ist die Zusage, dass *dieser* Stundenentwurf in den Jahresplan gehört — ohne den Entwurf
gibt es nichts zuzusagen. `ue_node_id` wird nur genullt (`SET NULL`): Verschwindet die
Unterrichtseinheit, bleibt die geplante Stunde für sich genommen sinnvoll.

Revision ID: 0067
Revises: 0066
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parked_lesson_content",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("halbjahr", sa.Integer(), nullable=False),
        # Der Termin, an dem der Inhalt lag.
        sa.Column("herkunft_datum", sa.Date(), nullable=False),
        sa.Column(
            "ue_node_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("context_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "stunde_node_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("context_nodes.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("thema", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("halbjahr IN (1, 2)", name="check_plc_halbjahr"),
    )
    # Gelesen wird immer je Gruppe und Halbjahr, sortiert nach Herkunft.
    op.create_index(
        "idx_parked_group_halbjahr",
        "parked_lesson_content",
        ["group_id", "halbjahr", "herkunft_datum"],
    )


def downgrade() -> None:
    op.drop_index("idx_parked_group_halbjahr", table_name="parked_lesson_content")
    op.drop_table("parked_lesson_content")
