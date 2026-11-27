"""Sammelimport (0.62, BH): Was aus einer Datei wird — immer ein Entwurf (Jan, 27.11.2026, F3)."""
from datetime import date

from app.context.curriculum_stapel import ERSETZT, NEU, ZUSAETZLICH, art_bestimmen, titel_zusatz

EINS = [{"id": "c1", "titel": "Chemie Kl. 8"}]


def test_nichts_vorhanden_neu():
    assert art_bestimmen([], 0, False) == (NEU, None)


def test_ein_veroeffentlichtes_wird_ersetzt():
    assert art_bestimmen(EINS, 0, False) == (ERSETZT, "c1")


def test_schon_ein_entwurf_zusaetzlich():
    assert art_bestimmen(EINS, 1, False) == (ZUSAETZLICH, None)
    assert art_bestimmen([], 1, False) == (ZUSAETZLICH, None)


def test_frueher_im_stapel_zusaetzlich():
    assert art_bestimmen([], 0, True) == (ZUSAETZLICH, None)
    assert art_bestimmen(EINS, 0, True) == (ZUSAETZLICH, None)


def test_mehrere_veroeffentlichte_ersetzen_keines():
    assert art_bestimmen(EINS + [{"id": "c2", "titel": "Chemie Kl. 8 Basis"}], 0, False) == (ZUSAETZLICH, None)


def test_titel_zusatz():
    assert titel_zusatz(date(2026, 11, 27)) == "Import 27.11.2026"


def test_mcp_kennt_quelle():
    """Die Entwürfe entstehen in einem KI-Programm über den MCP-Server — es muss `quelle` kennen."""
    from app.mcp.server import ANLEITUNG
    from app.mcp.werkzeuge import YAML_FORMAT

    assert "quelle" in YAML_FORMAT and "300 Zeichen" in YAML_FORMAT
    assert "quelle" in ANLEITUNG
