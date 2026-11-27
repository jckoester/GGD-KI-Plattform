"""Absprachen zwischen Fächern am Kapitel (0.63, AY Teil 2, Schritt 1): Prüfen und Bereinigen."""
import uuid

import pytest

from app.context.absprachen import ARTEN, GEGENART, MAX_JE_KAPITEL, MAX_TEXT, normalisieren

KAP = str(uuid.uuid4())


def _a(**abw):
    return {"fach_code": "ph", "kapitel_id": KAP, "art": "vorher", "text": " Bruchrechnung zuerst ", **abw}


def test_bereinigt_und_vergibt_kennung():
    [a] = normalisieren([_a()], "M")
    assert (a["fach_code"], a["kapitel_id"], a["art"], a["text"]) == ("PH", KAP, "vorher", "Bruchrechnung zuerst")
    assert uuid.UUID(a["id"]) and a["kapitel_titel"] is None
    # Eine vorhandene Kennung bleibt
    assert normalisieren([{**a}], "M")[0]["id"] == a["id"]


def test_leer_und_falsche_form():
    assert normalisieren(None) == []
    assert normalisieren([]) == []
    with pytest.raises(ValueError, match="Liste"):
        normalisieren({"fach_code": "PH"})
    with pytest.raises(ValueError, match="Absprache 1: muss ein Objekt"):
        normalisieren(["PH"])


def test_fach_pflicht_und_nicht_das_eigene():
    with pytest.raises(ValueError, match="Absprache 1: Das andere Fach fehlt"):
        normalisieren([_a(fach_code=" ")])
    with pytest.raises(ValueError, match="nicht dem eigenen"):
        normalisieren([_a(fach_code="m")], "M")


def test_arten():
    assert set(ARTEN) == set(GEGENART) and GEGENART["vorher"] == "nachher" and GEGENART["gleichzeitig"] == "gleichzeitig"
    with pytest.raises(ValueError, match="Art „bald“ gibt es nicht"):
        normalisieren([_a(art="bald")])


def test_zeitlich_braucht_kapitel_abgestimmt_braucht_text():
    for art in ("vorher", "gleichzeitig", "nachher"):
        with pytest.raises(ValueError, match="braucht ein Kapitel"):
            normalisieren([_a(art=art, kapitel_id=None)])
    # Ein Titel ohne Kennung genügt (YAML, Ziel nicht aufgelöst)
    assert normalisieren([_a(kapitel_id=None, kapitel_titel="Dichte")])[0]["kapitel_titel"] == "Dichte"
    with pytest.raises(ValueError, match="Text — er fehlt"):
        normalisieren([_a(art="abgestimmt", kapitel_id=None, text="")])
    assert normalisieren([_a(art="abgestimmt", kapitel_id=None, text="Begriffe einheitlich")])[0]["kapitel_id"] is None


def test_grenzen_und_doppelte():
    with pytest.raises(ValueError, match="zu lang"):
        normalisieren([_a(text="x" * (MAX_TEXT + 1))])
    with pytest.raises(ValueError, match=f"Höchstens {MAX_JE_KAPITEL}"):
        normalisieren([_a(kapitel_id=str(uuid.uuid4())) for _ in range(MAX_JE_KAPITEL + 1)])
    with pytest.raises(ValueError, match="Absprache 2: Dieselbe Absprache"):
        normalisieren([_a(), _a(text="anders")])
    with pytest.raises(ValueError, match="keine gültige Kennung"):
        normalisieren([_a(kapitel_id="kapitel-3")])
    # Doppelte Kennung (kopierte Zeile) → neue Kennung statt Fehler
    erst = normalisieren([_a()])[0]
    zwei = normalisieren([erst, {**erst, "art": "nachher"}])
    assert zwei[0]["id"] != zwei[1]["id"]
