"""`update_lesson_phases` für Skizzen (0.15, Päckchen A Schritt 5, Plan F5).

Eine Skizze der Lehrkraft hat oft noch keine Minuten. Das Werkzeug verlangte sie bis 0.15 im
Schema; das Modell musste sie erfinden. Jetzt ist `dauer_min` optional — und das Werkzeug
prüft die Phasen erstmals selbst, nach derselben Regel wie der Planer (`LessonPhaseItem`).
"""
import pytest

import app.chat.router  # noqa: F401 — füllt TOOL_REGISTRY
from app.chat.tools import TOOL_REGISTRY
from app.planning.assistant_tools import _phasen_pruefen


def _phasen_fehler(phasen):
    return _phasen_pruefen(phasen)[1]


def _funktion():
    return TOOL_REGISTRY["update_lesson_phases"].definition["function"]


def test_dauer_ist_nicht_mehr_pflicht():
    phase = _funktion()["parameters"]["properties"]["phasen"]["items"]
    assert phase["required"] == ["name"]
    assert phase["properties"]["dauer_min"]["minimum"] == 1


def test_die_beschreibung_nennt_die_regeln():
    """Was das Modell wissen muss, steht in der Beschreibung — der Prompt kommt erst in
    Schritt 6, und ein selbst angelegter Assistent hat vielleicht keinen."""
    text = _funktion()["description"]
    assert "id" in text and "unverändert" in text            # Kennungen behalten
    assert "nie 0" in text                                    # Skizze ohne Dauer
    assert "vokabular aus get_lesson_detail" in text          # Vokabular kommt mit dem Entwurf
    assert "{typ:'node'" in text and "{typ:'text'" in text    # node vs. text
    assert "refs nur setzen, wenn die Lehrkraft zugestimmt hat" in text


@pytest.mark.parametrize("phasen", [
    [{"name": "Einstieg"}],
    [{"name": "Einstieg", "dauer_min": None}],
    [{"name": "Einstieg", "dauer_min": 10, "prio": "uebung"}],
    # Was der Editor darüber hinaus schickt, stört nicht — es zählt nur nicht (P2).
    [{"name": "Einstieg", "status": "offen", "sozialform": {"typ": "text", "wert": "EA"}}],
    [],
])
def test_gueltige_phasen(phasen):
    assert _phasen_fehler(phasen) is None


@pytest.mark.parametrize("dauer", [0, -5, 481, "zehn"])
def test_unbrauchbare_dauer(dauer):
    fehler = _phasen_fehler([{"name": "Einstieg", "dauer_min": 10},
                             {"name": "Erarbeitung", "dauer_min": dauer}])
    assert fehler.startswith("Phase 2 („Erarbeitung“): dauer_min")
    assert "nie 0" in fehler


@pytest.mark.parametrize("phasen,teil", [
    ([{"dauer_min": 10}], "name"),
    ([{"name": ""}], "name"),
    ([{"name": "Einstieg", "prio": "wichtig"}], "Prio"),
    ([{"name": "Einstieg", "methode": "Gruppenpuzzle"}], "methode"),
    ("Einstieg, Erarbeitung", "Liste"),
])
def test_andere_fehler(phasen, teil):
    assert teil in _phasen_fehler(phasen)


def test_gespeichert_wird_die_form_des_planers():
    """Eine weggelassene Dauer steht als null da; Zusatzfelder des Modells fallen weg — sie
    gehören der Nachbereitung (`uebernimm_zusatzfelder` holt sie aus der gespeicherten Phase)."""
    phasen, fehler = _phasen_pruefen([{"name": "Einstieg", "status": "offen"}])
    assert fehler is None
    assert phasen[0]["dauer_min"] is None and phasen[0]["prio"] == "kern"
    assert "status" not in phasen[0]
