"""Dieselbe Rangfolge an drei Stellen (Paket 7, AP7).

`private` < `group_teachers` < `group` < `subject` < `school` < `global` steht

1. als CHECK-Bedingung in der **Datenbank** (Alembic `0074`),
2. noch einmal als `CheckConstraint`-Text im **Modell** (`app/db/models.py`),
3. und ein drittes Mal als `_SCOPE_RANG` in der **Startprüfung**
   (`app/context/taxonomy_check.py`).

⚠️ **Eine vierte Kopie stand im Test und ist entfernt** — sie fiel nur auf, weil sie beim
neuen Wert `group_teachers` mit `KeyError` abbrach. Hätte sie ihn gekannt und **falsch**
eingeordnet, wäre sie still durchgelaufen: Der Test hätte eine Ordnung bestätigt, die es
nicht gibt.

Zusammenführen geht nicht — Migrationen bleiben eingefroren, und das Modell beschreibt,
was `create_all` bauen würde. **Prüfen geht.** Was die Rangfolge bedeutet: Wer schreiben
darf, muss auch lesen dürfen (`write_rang <= read_rang`).

Die dritte Stelle — die echte Bedingung in der laufenden Datenbank — prüft
`tests/integration/test_scope_rangfolge_db.py`; dafür braucht es eine Datenbank.
"""

import re

from app.context.taxonomy_check import _SCOPE_RANG
from app.db.models import ContextNode


def _bedingungstext() -> str:
    for c in ContextNode.__table__.constraints:
        if getattr(c, "name", None) == "check_context_nodes_scope_restrictivity":
            return str(c.sqltext)
    raise AssertionError("CheckConstraint `check_context_nodes_scope_restrictivity` fehlt")


def _raenge_aus(text: str) -> list[dict[str, int]]:
    """Die `CASE`-Zuordnungen — eine je Vorkommen (write und read).

    ⚠️ **Beide getrennt.** Sie stehen zweimal fast gleich da; genau dort entsteht der
    Tippfehler, den niemand sieht. Ein Test, der nur das erste `CASE` liest, ginge
    durch, während die beiden Hälften verschiedene Ordnungen benutzen.
    """
    bloecke = re.findall(r"CASE\s+(?:write_scope|read_scope)(.*?)END", text, re.S)
    assert len(bloecke) == 2, f"Erwartet: je ein CASE für write und read, gefunden {len(bloecke)}"
    return [
        {name: int(rang) for name, rang in re.findall(r"WHEN '(\w+)' THEN (\d+)", block)}
        for block in bloecke
    ]


def test_modell_und_startpruefung_tragen_dieselbe_ordnung():
    schreiben, lesen = _raenge_aus(_bedingungstext())
    assert schreiben == _SCOPE_RANG, (
        "Die Rangfolge im Modell (write) weicht von `_SCOPE_RANG` ab: "
        f"{schreiben} ≠ {_SCOPE_RANG}"
    )
    assert lesen == _SCOPE_RANG, (
        "Die Rangfolge im Modell (read) weicht von `_SCOPE_RANG` ab: "
        f"{lesen} ≠ {_SCOPE_RANG}"
    )


def test_group_teachers_liegt_zwischen_privat_und_gruppe():
    """Der Wert, der die Ordnung am 24.09.2026 entschieden hat — namentlich festgehalten.

    Die allgemeine Prüfung oben ließe sich stilllegen, indem jemand *beide* Seiten gleich
    falsch ändert. Diese hier nicht: Läge `group_teachers` über `group`, dürfte eine
    Lehrkraft Planungsknoten schreiben, die alle Gruppenmitglieder lesen — genau die
    Freigabe, die im September zurückgenommen wurde.
    """
    assert _SCOPE_RANG["private"] < _SCOPE_RANG["group_teachers"] < _SCOPE_RANG["group"]
    assert _SCOPE_RANG["group"] < _SCOPE_RANG["subject"] < _SCOPE_RANG["school"]
    assert _SCOPE_RANG["school"] < _SCOPE_RANG["global"]
