"""Dieselbe Relationsliste an zwei Orten im Backend (Paket 9, AP2).

`ERLAUBTE_RELATIONEN` (`app/context/metadata.py`) ist die Zusage der Anwendung, der
CHECK-Constraint im Modell ihre Durchsetzung. Beide waren schon einmal auseinander:
`reflects_on` fiel mit Alembic 0056 weg, weil der zugehörige Knotentyp gestrichen wurde.

⚠️ **Dieselbe Familie wie die Scope-Rangfolge** (`test_scope_rangfolge.py`): eine Regel,
die an mehreren Stellen steht und nur beim Benutzen auffällt, wenn sie auseinanderläuft.
Eine Relation, die nur die Anwendung kennt, scheitert beim Speichern; eine, die nur die
Datenbank kennt, bietet niemand an.

Die **dritte** Stelle — die Bedingung in der laufenden Datenbank — prüft
`tests/integration/test_relation_is_a.py`; dafür braucht es eine Datenbank. Die
**vierte**, eine Liste im Frontend-Test `collections.test.js`, lässt sich von hier nicht
erreichen und ist dort vermerkt.
"""

import re

from app.context.metadata import ERLAUBTE_RELATIONEN
from app.db.models import ContextEdge


def _aus_dem_modell() -> set[str]:
    for c in ContextEdge.__table__.constraints:
        if getattr(c, "name", None) == "check_context_edges_relation":
            return set(re.findall(r"'(\w+)'", str(c.sqltext)))
    raise AssertionError("CheckConstraint `check_context_edges_relation` fehlt")


def test_modell_und_anwendung_kennen_dieselben_relationen():
    assert _aus_dem_modell() == set(ERLAUBTE_RELATIONEN), (
        f"Modell: {sorted(_aus_dem_modell())} · "
        f"ERLAUBTE_RELATIONEN: {sorted(ERLAUBTE_RELATIONEN)}"
    )


def test_is_a_ist_dabei():
    """Namentlich festgehalten — die allgemeine Prüfung oben ginge auch durch, wenn
    beide Seiten `is_a` gemeinsam verlören."""
    assert "is_a" in ERLAUBTE_RELATIONEN
    assert "is_a" in _aus_dem_modell()
