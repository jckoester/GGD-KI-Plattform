"""Darstellungsstufen: Zuordnung aus `config/ui_levels.yaml` (Schritt 1).

Die Datei entscheidet, ab welcher Stufe ein Navigationseintrag erscheint. Sie ist
absichtlich ohne Release änderbar — und genau deshalb muss der Lader die Fehler abfangen,
die dabei entstehen. Alle vier hier geprüften Fehlerbilder haben dieselbe Eigenschaft:
Sie sind **stumm**. Ein Tippfehler lässt einen Eintrag verschwinden, eine Lücke in der
Nummerierung lässt eine Stufe überspringen — ohne Fehlermeldung wäre die Ursache kaum zu
finden.

Geprüft wird gegen `ui_levels.example.yaml`: Die lokale `ui_levels.yaml` gehört der
jeweiligen Schule und darf abweichen.
"""
import pytest
import yaml
from pydantic import ValidationError

from app.core.paths import aufloesen
from app.ui.levels import (
    BEKANNTE_EINTRAEGE,
    RollenStufen,
    UiLevels,
    load_ui_levels,
    stufe_fuer,
)

BEISPIEL = aufloesen("config/ui_levels.example.yaml")


def _rolle(**abweichung) -> dict:
    basis = {
        "startstufe": 1,
        "stufen": [
            {"stufe": 1, "name": "A", "beschreibung": "…", "eintraege": ["chat"]},
            {"stufe": 2, "name": "B", "beschreibung": "…", "eintraege": ["library"]},
        ],
    }
    basis.update(abweichung)
    return basis


# ── Die ausgelieferte Vorlage ─────────────────────────────────────────────────

def test_beispieldatei_laedt():
    cfg = UiLevels.model_validate(yaml.safe_load(BEISPIEL.read_text(encoding="utf-8")))
    assert set(cfg.rollen) == {"student", "teacher"}


def test_beide_rollen_starten_auf_stufe_1():
    """Entscheidung Jan, 19.09.2026: die kleinste Fassung ist die übersichtlichste."""
    cfg = UiLevels.model_validate(yaml.safe_load(BEISPIEL.read_text(encoding="utf-8")))
    assert cfg.rollen["student"].startstufe == 1
    assert cfg.rollen["teacher"].startstufe == 1


def test_schuelerinnen_sehen_bibliothek_und_wissen_erst_auf_stufe_2():
    """Der Kern der Entscheidung: Was am Anfang leer ist, kostet nur Aufmerksamkeit."""
    cfg = UiLevels.model_validate(yaml.safe_load(BEISPIEL.read_text(encoding="utf-8")))
    stufe1 = cfg.rollen["student"].eintraege_bis(1)
    assert "library" not in stufe1
    assert "knowledge" not in stufe1
    # Werkzeuge bleiben unten — sie benutzen sich wie Assistenten (Entscheidung 19.09.).
    assert "tools" in stufe1

    stufe2 = cfg.rollen["student"].eintraege_bis(2)
    assert {"library", "knowledge"} <= set(stufe2)


def test_lehrkraefte_bekommen_planung_erst_auf_stufe_3():
    cfg = UiLevels.model_validate(yaml.safe_load(BEISPIEL.read_text(encoding="utf-8")))
    lehrkraft = cfg.rollen["teacher"]
    assert "planner" not in lehrkraft.eintraege_bis(2)
    assert "planner" in lehrkraft.eintraege_bis(3)


def test_die_hoechste_lehrkraft_stufe_zeigt_alles():
    """Sonst gäbe es Funktionen, die über die Navigation nie erreichbar sind."""
    cfg = UiLevels.model_validate(yaml.safe_load(BEISPIEL.read_text(encoding="utf-8")))
    lehrkraft = cfg.rollen["teacher"]
    assert set(lehrkraft.eintraege_bis(lehrkraft.hoechste)) == set(BEKANNTE_EINTRAEGE)


# ── Die stummen Fehler ────────────────────────────────────────────────────────

def test_tippfehler_im_eintrag_wird_abgewiesen():
    """`libary` statt `library` ließe die Bibliothek lautlos verschwinden."""
    daten = _rolle(stufen=[
        {"stufe": 1, "name": "A", "beschreibung": "…", "eintraege": ["libary"]},
    ])
    with pytest.raises(ValidationError, match="unbekannte Navigationseinträge"):
        RollenStufen.model_validate(daten)


def test_luecke_in_der_nummerierung_wird_abgewiesen():
    daten = _rolle(stufen=[
        {"stufe": 1, "name": "A", "beschreibung": "…", "eintraege": ["chat"]},
        {"stufe": 3, "name": "C", "beschreibung": "…", "eintraege": ["library"]},
    ])
    with pytest.raises(ValidationError, match="lückenlos"):
        RollenStufen.model_validate(daten)


def test_eintrag_in_zwei_stufen_wird_abgewiesen():
    """Sonst wäre unbestimmt, ab wann er erscheint."""
    daten = _rolle(stufen=[
        {"stufe": 1, "name": "A", "beschreibung": "…", "eintraege": ["chat"]},
        {"stufe": 2, "name": "B", "beschreibung": "…", "eintraege": ["chat"]},
    ])
    with pytest.raises(ValidationError, match="Stufe 1 und 2"):
        RollenStufen.model_validate(daten)


def test_startstufe_muss_es_geben():
    with pytest.raises(ValidationError, match="startstufe 5"):
        RollenStufen.model_validate(_rolle(startstufe=5))


# ── Kumulation und Rollenwahl ─────────────────────────────────────────────────

def test_stufen_sind_kumulativ():
    r = RollenStufen.model_validate(_rolle())
    assert r.eintraege_bis(1) == ["chat"]
    assert r.eintraege_bis(2) == ["chat", "library"]


def test_admin_zaehlt_als_lehrkraft():
    """Admin ist eine Erweiterung der Lehrkraft-Rolle, kein eigener Nutzertyp."""
    cfg = load_ui_levels()
    assert cfg.fuer(["admin", "teacher"]) is cfg.rollen["teacher"]


def test_lehrkraft_gewinnt_vor_schuelerin():
    cfg = load_ui_levels()
    assert cfg.fuer(["student", "teacher"]) is cfg.rollen["teacher"]


def test_unbekannte_rolle_bekommt_keine_stufen():
    """`None` heißt für die Oberfläche: alles zeigen — lieber zu viel als eine leere Navigation."""
    cfg = load_ui_levels()
    assert cfg.fuer(["review"]) is None


# ── Der Endpunkt ──────────────────────────────────────────────────────────────

def _client(roles: list[str]):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.auth.dependencies import get_current_user
    from app.auth.jwt import JwtPayload
    from app.ui.router import router as ui_router

    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: JwtPayload(
        sub="p", roles=roles, grade=None, jti="j", iat=1, exp=9_999_999_999
    )
    app.include_router(ui_router)
    return TestClient(app)


def test_endpunkt_liefert_die_stufen_der_eigenen_rolle():
    daten = _client(["student"]).get("/ui/levels").json()
    assert daten["rolle"] == "student"
    assert daten["startstufe"] == 1
    assert [s["stufe"] for s in daten["stufen"]] == [1, 2]


def test_endpunkt_gibt_der_lehrkraft_ihre_vier_stufen():
    daten = _client(["teacher"]).get("/ui/levels").json()
    assert daten["rolle"] == "teacher"
    assert daten["hoechste"] == 4


def test_endpunkt_nennt_den_aufwand_wo_es_einen_gibt():
    """Ohne die Angabe schaltet jemand frei und steht vor einer leeren Seite."""
    stufen = {s["stufe"]: s for s in _client(["teacher"]).get("/ui/levels").json()["stufen"]}
    assert "Wochenraster" in (stufen[3]["aufwand"] or "")


def test_endpunkt_bleibt_bei_unbekannter_rolle_leer():
    daten = _client(["review"]).get("/ui/levels").json()
    assert daten["rolle"] is None
    assert daten["stufen"] == []


# ── Die wirksame Stufe (`stufe_fuer`) ─────────────────────────────────────────

def test_ohne_gesetzte_stufe_gilt_die_startstufe():
    """Nach der Nachfüllung (Alembic 0064) heißt „nicht gesetzt" verlässlich „neu"."""
    assert stufe_fuer({}, ["teacher"]) == 1
    assert stufe_fuer({}, ["student"]) == 1


def test_gesetzte_stufe_gilt():
    assert stufe_fuer({"ui_level": 3}, ["teacher"]) == 3


@pytest.mark.parametrize("wert,erwartet", [(0, 1), (-5, 1), (99, 4)])
def test_beim_lesen_wird_geklemmt(wert, erwartet):
    """Ein Altwert darf nie eine leere Navigation erzeugen — 0 wäre genau das.

    Anders als beim Schreiben, wo ein solcher Wert abgewiesen wird: Dort ist er ein
    Fehler, hier nur ein Fund aus einer älteren Konfiguration.
    """
    assert stufe_fuer({"ui_level": wert}, ["teacher"]) == erwartet


@pytest.mark.parametrize("wert", ["abc", None, [], {}])
def test_unlesbarer_wert_faellt_auf_die_startstufe(wert):
    assert stufe_fuer({"ui_level": wert}, ["teacher"]) == 1


def test_zahl_als_zeichenkette_wird_gelesen():
    """JSONB gibt zurück, was hineingeschrieben wurde — auch `"2"`."""
    assert stufe_fuer({"ui_level": "2"}, ["student"]) == 2


def test_rolle_ohne_stufen_liefert_None_statt_1():
    """`None` heißt „kein Filter", nicht „niedrigste Stufe".

    Gäbe die Funktion hier 1 zurück, verschwände für eine unbekannte Rolle
    stillschweigend fast die ganze Navigation.
    """
    assert stufe_fuer({"ui_level": 3}, ["review"]) is None
