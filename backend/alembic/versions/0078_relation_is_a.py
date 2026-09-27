"""Relation `is_a` — „ist ein(e)" als eigene Kantenart

Revision ID: 0078
Revises: 0077
Create Date: 2026-09-26

⚠️ **Warum eine eigene Relation und nicht `related_to` mit Kanten-Metadata**
(Entscheidung Jan, 26.09.2026, Paket 9/E1): Hierarchie ist eine eigene Beziehungsart.
Graphansicht und Traversierung sind laut ADR-013 immer **relationstyp-gefiltert** — „alle
Unterbegriffe von Gemisch" oder eine Oberbegriffskette als Lernpfad wären über
`related_to` nur per Kanten-Metadata filterbar, also nicht im Graphen, sondern daneben.

**Abgrenzung zu `part_of`:** „Teil von" ist nicht „ist ein". Ein Natriumion ist *Teil*
eines Ionengitters; Natriumchlorid *ist ein* Salz.

**Keine Transitivität im Datenmodell.** Eine Kette entsteht durch Traversierung (zwei,
drei Hops wie bei allen Kanten), nicht durch abgeleitete Kanten. Und die Kante zeigt auf
eine **bestimmte Fassung** eines Begriffs: „Redoxreaktion (Elektronenübergang)" ist etwas
anderes als „Redoxreaktion (Sauerstoffübertragung)".

**Bestand:** keiner — die Relation ist neu. Die Rückrolle verlangt deshalb nur, dass
niemand sie inzwischen benutzt hat; sie löscht keine Kanten, sondern lässt den
`ALTER TABLE` scheitern, falls doch welche existieren. Das ist die richtige Richtung:
Eine Rückrolle, die Wissen still wegwirft, ist schlimmer als eine, die anhält.
"""
from alembic import op

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None

_ALT = (
    "relation IN ('requires','used_with','part_of','develops',"
    "'supersedes','references','follows','derived_from','related_to')"
)
_NEU = (
    "relation IN ('requires','used_with','part_of','develops',"
    "'supersedes','references','follows','derived_from','related_to','is_a')"
)


def _setze(bedingung: str) -> None:
    op.execute(
        "ALTER TABLE context_edges DROP CONSTRAINT IF EXISTS check_context_edges_relation"
    )
    op.execute(
        "ALTER TABLE context_edges ADD CONSTRAINT check_context_edges_relation "
        f"CHECK ({bedingung})"
    )


def upgrade() -> None:
    _setze(_NEU)


def downgrade() -> None:
    _setze(_ALT)
