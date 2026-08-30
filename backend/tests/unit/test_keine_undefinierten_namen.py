"""Namen, die es zur Laufzeit nicht gibt — der Container startet sonst nicht.

Anlass (30.08.2026, auf dem Produktivsystem): `app/chat/router.py` benutzte `Any` in einer
Annotation, ohne es zu importieren. Hier liefen **alle** Tests grün, im Container brach der
Import des Backends ab (`NameError: name 'Any' is not defined`) und der Dienst kam nicht
hoch.

**Warum die Testsuite das nicht sehen kann:** Die Entwicklungs-venv läuft auf Python 3.14,
das Container-Image auf 3.12 (`FROM python:3.12-slim`). Seit 3.14 werden Annotationen erst
bei Bedarf ausgewertet (PEP 649) — ein undefinierter Name darin fällt dort nie auf. Unter
3.12 wird die Annotation beim Definieren der Funktion ausgewertet und der Import stirbt.

Diese Prüfung ist deshalb **statisch**: Sie liest den Quelltext, statt ihn auszuführen, und
ist damit unabhängig von der Python-Fassung, unter der sie läuft. Solange dev und Container
verschiedene Fassungen fahren, ist sie die einzige Stelle, an der diese Fehlerklasse hier
auffällt.

Geprüft wird, was in einem Container landet — das Backend, seine Skripte und die
Guardrail-Module, die im LiteLLM-Container liegen. Ein undefinierter Name in letzteren
hielte den Proxy vom Start ab und damit die ganze Schule.
"""
from pathlib import Path

import pytest
from pyflakes import api as pyflakes_api
from pyflakes import messages as pyflakes_messages

REPO = Path(__file__).resolve().parents[3]

# Verzeichnisse, deren Code in einem Container ausgeführt wird.
GEPRUEFT = (
    REPO / "backend" / "app",
    REPO / "backend" / "scripts",
    REPO / "scripts",
    REPO / "infra" / "guardrails",
)

# Nur diese Klassen. Ungenutzte Importe und Schattierungen meldet pyflakes ebenfalls —
# das ist Kosmetik und würde die Prüfung zu einem Stilwächter machen, den irgendwann
# niemand mehr ernst nimmt. Hier geht es allein um Namen, die zur Laufzeit fehlen.
FEHLENDE_NAMEN = (
    pyflakes_messages.UndefinedName,
    pyflakes_messages.UndefinedLocal,
    pyflakes_messages.UndefinedExport,
)


# Fremdcode gehört nicht in die Prüfung. Unter `scripts/` liegt die venv des Scrapers
# (`.venv-scraper`), und deren Pakete melden reichlich — `typing_extensions` etwa listet
# in `__all__` Namen, die es je nach Python-Fassung gar nicht gibt. Ohne diesen Filter
# ertränke das echte Funde.
UEBERSPRUNGEN = {"__pycache__", "venv", "node_modules", "site-packages"}


def _gehoert_uns(datei: Path, wurzel: Path) -> bool:
    """Geprüft wird der Pfad **unterhalb** des Suchverzeichnisses.

    Der absolute Pfad taugt dafür nicht: Er enthält Bestandteile, die niemand in der Hand
    hat — ein Verzeichnis mit Punkt im Namen oberhalb des Repos schlösse sonst alles aus.
    """
    return not any(
        teil in UEBERSPRUNGEN or teil.startswith(".")
        for teil in datei.relative_to(wurzel).parts
    )


class _Sammler:
    """Reporter-Schnittstelle von pyflakes, die nur einsammelt statt zu drucken."""

    def __init__(self) -> None:
        self.namen: list[str] = []
        self.syntax: list[str] = []

    def flake(self, message) -> None:
        if isinstance(message, FEHLENDE_NAMEN):
            self.namen.append(str(message))

    def syntaxError(self, filename, msg, lineno, offset, text) -> None:
        self.syntax.append(f"{filename}:{lineno}: {msg}")

    def unexpectedError(self, filename, msg) -> None:
        self.syntax.append(f"{filename}: {msg}")


def _pruefe(*pfade: Path) -> _Sammler:
    sammler = _Sammler()
    for pfad in pfade:
        for datei in sorted(pfad.rglob("*.py")):
            if not _gehoert_uns(datei, pfad):
                continue
            pyflakes_api.checkPath(str(datei), sammler)
    return sammler


@pytest.fixture(scope="module")
def ergebnis() -> _Sammler:
    return _pruefe(*GEPRUEFT)


def test_keine_undefinierten_namen(ergebnis):
    """Jeder benutzte Name muss importiert oder definiert sein — auch in Annotationen."""
    assert ergebnis.namen == [], (
        "Undefinierte Namen gefunden. Unter Python 3.12 im Container bricht damit der "
        "Import ab, hier unter 3.14 nicht (PEP 649):\n  " + "\n  ".join(ergebnis.namen)
    )


def test_kein_syntaxfehler(ergebnis):
    """Nebenbefund derselben Prüfung — eine Datei, die nicht parst, startet nirgends."""
    assert ergebnis.syntax == [], "Nicht lesbare Dateien:\n  " + "\n  ".join(ergebnis.syntax)


def test_die_pruefung_greift_ueberhaupt(tmp_path):
    """Gegenprobe im Test selbst.

    Ohne sie wäre nicht zu unterscheiden, ob der Quelltext sauber ist oder die Prüfung
    ins Leere läuft — etwa weil pyflakes seine Meldungsklassen umbenennt oder die
    Reporter-Schnittstelle sich ändert. Beides bliebe sonst als grüner Test stehen.
    """
    (tmp_path / "beispiel.py").write_text(
        "def f(x: Any) -> None:\n    return None\n", encoding="utf-8"
    )
    befund = _pruefe(tmp_path)
    assert len(befund.namen) == 1 and "Any" in befund.namen[0]
