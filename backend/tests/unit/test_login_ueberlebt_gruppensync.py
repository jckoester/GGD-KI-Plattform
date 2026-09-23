"""Ein Fehler im Gruppen-Sync darf die Anmeldung nicht verhindern.

**Warum das ein eigener Wächter ist.** Bis zum 23.09.2026 lief `sync_groups` ungeschützt
im Login-Pfad. Eine Ausnahme darin — die damals vorhandene Adoptionsheuristik warf bei
zwei Gruppen desselben Fachs `MultipleResultsFound` — endete als HTTP 500, und die
Lehrkraft kam nicht hinein.

Die Kopplung war unabhängig von jenem Befund falsch: **Rollen und Budget stehen im
Token**, die Gruppen sind Komfort. Geprüft wird über den Syntaxbaum, nicht per
Textsuche — ein `try` an anderer Stelle der Datei soll nicht mitzählen.
"""
import ast
from pathlib import Path

import pytest

ROUTER = Path(__file__).resolve().parents[2] / "app" / "auth" / "router.py"


def _aufrufe_mit_schutz():
    """Jeder `sync_groups`-Aufruf mit der Angabe, ob er in einem `try` steht."""
    baum = ast.parse(ROUTER.read_text(encoding="utf-8"))
    ergebnis = []

    def geh(knoten, im_try: bool):
        for kind in ast.iter_child_nodes(knoten):
            if isinstance(kind, ast.Call):
                ziel = kind.func
                name = getattr(ziel, "id", None) or getattr(ziel, "attr", None)
                if name == "sync_groups":
                    ergebnis.append(im_try)
            if isinstance(kind, ast.Try):
                for teil in kind.body:
                    geh(teil, True)
                for teil in kind.handlers + kind.orelse + kind.finalbody:
                    geh(teil, im_try)
            else:
                geh(kind, im_try)

    geh(baum, False)
    return ergebnis


def test_es_gibt_ueberhaupt_aufrufe():
    """Sonst wäre der Wächter unten leer und trotzdem grün."""
    assert _aufrufe_mit_schutz(), "Kein `sync_groups`-Aufruf im Login-Router gefunden"


def test_jeder_gruppensync_im_login_ist_abgesichert():
    aufrufe = _aufrufe_mit_schutz()
    assert all(aufrufe), (
        f"{aufrufe.count(False)} von {len(aufrufe)} `sync_groups`-Aufrufen laufen "
        "ungeschützt — ein Fehler bei der Gruppenzuordnung sperrt dann die Anmeldung."
    )
