"""Relation `reflects_on` aus dem CHECK-Constraint entfernen.

Sie gehörte zum Knotentyp `reflexion`, den Migration 0055 gestrichen hat: Die
Nachbereitung einer Stunde steht seither als `metadata.reflexion` an der Stunde selbst,
nicht als eigener Knoten mit einer Kante zurück. Ohne Erzeuger und ohne Bestand ist die
Relation ein Angebot, das die Anwendung nicht mehr einlöst — und der Verknüpfen-Dialog
könnte sie versehentlich wieder anbieten, weil `ERLAUBTE_RELATIONEN` sich am Constraint
orientiert.

Der Constraint ist die einzige Stelle, die Relationen begrenzt; `relation` ist eine
gewöhnliche Textspalte.

⚠️ **Abbruch statt Datenverlust.** Gibt es entgegen der Erwartung noch `reflects_on`-
Kanten, bricht der Lauf mit einer Meldung ab, die sagt, wie viele es sind. Sie stumm zu
löschen wäre der falsche Weg: Eine Kante, die es laut Modell nicht geben kann, aber gibt,
ist ein Befund und keine Altlast.

Revision ID: 0056
Revises: 0055
"""
from alembic import op
import sqlalchemy as sa

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

# Die zehnte Relation fällt weg — die übrigen neun bleiben in unveränderter Reihenfolge.
UEBRIG = (
    "'requires', 'used_with', 'part_of', 'develops', "
    "'supersedes', 'references', 'follows', 'derived_from', 'related_to'"
)
MIT_REFLECTS_ON = (
    "'requires', 'used_with', 'part_of', 'develops', "
    "'supersedes', 'references', 'follows', 'reflects_on', "
    "'derived_from', 'related_to'"
)


def _setze_constraint(werte: str) -> None:
    op.execute(
        f"""
        ALTER TABLE context_edges
        DROP CONSTRAINT check_context_edges_relation,
        ADD CONSTRAINT check_context_edges_relation
            CHECK (relation IN ({werte}))
        """
    )


def upgrade():
    anzahl = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM context_edges WHERE relation = 'reflects_on'"))
        .scalar()
    )
    if anzahl:
        raise RuntimeError(
            f"{anzahl} Kanten mit relation='reflects_on' vorhanden. Die Relation gehörte "
            "zum in Migration 0055 gestrichenen Knotentyp `reflexion` und sollte im "
            "Bestand nicht mehr vorkommen. Bitte prüfen, woher sie stammen, und die "
            "Kanten von Hand auflösen oder löschen — dann diese Migration erneut laufen "
            "lassen."
        )
    _setze_constraint(UEBRIG)


def downgrade():
    # Ein Constraint zu **erweitern** kann nie an vorhandenen Zeilen scheitern — anders
    # als bei 0055 ist die Rücknahme hier gefahrlos.
    _setze_constraint(MIT_REFLECTS_ON)
