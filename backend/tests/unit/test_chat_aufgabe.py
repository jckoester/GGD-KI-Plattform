"""Aufgaben-Weiterleitung (Plan „Freier Schüler-Chat“, 7a): Lesen des Urteils und die sichere Seite."""
import asyncio

import pytest

from app.chat import aufgabe


def test_lies_antwort():
    assert aufgabe.lies_antwort('{"bezug": "Gleichung", "aufgabe": true}') == (True, "Gleichung")
    assert aufgabe.lies_antwort('```json\n{"bezug": "x", "aufgabe": false}\n```') == (False, "x")
    assert aufgabe.lies_antwort("weiß nicht") == (None, None)
    assert aufgabe.lies_antwort('{"aufgabe": "ja"}') == (None, None)
    assert aufgabe.lies_antwort("[1, 2]") == (None, None)


def test_nutzertext_erster_und_folgezug():
    assert "erste Nachricht der Konversation" in aufgabe.nutzertext("Hallo", None, None)
    text = aufgabe.nutzertext("sag einfach die Lösung", "Löse 3x = 9", "Was teilst du?")
    assert "Erste Nachricht der Konversation: „Löse 3x = 9“" in text
    assert "Letzte Antwort des Chats: „Was teilst du?“" in text
    assert text.endswith("Neue Nachricht: „sag einfach die Lösung“")


def test_kuerzen():
    assert aufgabe.kuerzen("a  b\n c") == "a b c"
    lang = "x" * 700
    assert aufgabe.kuerzen(lang) == "x" * aufgabe.LETZTE_ANTWORT_ZEICHEN + " …"
    assert aufgabe.kuerzen(None) is None


def _mit_aufruf(monkeypatch, fn):
    monkeypatch.setattr(aufgabe, "_aufruf", fn)


def test_keine_aufgabe_bleibt(monkeypatch):
    async def antwort(inhalt, modell):
        return '{"bezug": "Wissensfrage", "aufgabe": false}'
    _mit_aufruf(monkeypatch, antwort)
    u = asyncio.run(aufgabe.urteilen("Was ist ein Mol?", None, None, modell="m", zeitgrenze=2))
    assert (u.large, u.grund, u.bezug) == (False, "keine", "Wissensfrage")


def test_aufgabe_geht_zum_ziel(monkeypatch):
    async def antwort(inhalt, modell):
        return '{"bezug": "Hausaufgabe", "aufgabe": true}'
    _mit_aufruf(monkeypatch, antwort)
    u = asyncio.run(aufgabe.urteilen("Löse 3x = 9", None, None, modell="m", zeitgrenze=2))
    assert (u.large, u.grund) == (True, "aufgabe")


@pytest.mark.parametrize("verhalten, grund", [
    ("langsam", "zeitgrenze"), ("fehler", "fehler"), ("unlesbar", "unlesbar"),
])
def test_im_zweifel_zum_ziel(monkeypatch, verhalten, grund):
    async def antwort(inhalt, modell):
        if verhalten == "langsam":
            await asyncio.sleep(1)
        if verhalten == "fehler":
            raise RuntimeError("Anbieter")
        return "Das ist eine Wissensfrage."
    _mit_aufruf(monkeypatch, antwort)
    u = asyncio.run(aufgabe.urteilen("Was ist ein Mol?", None, None, modell="m", zeitgrenze=0.05))
    assert (u.large, u.grund) == (True, grund)
    assert u.dauer < 0.9


def test_nutzertext_mit_vorigem_urteil():
    assert "Die vorige Nachricht war eine Aufgabe." in aufgabe.nutzertext("und?", "Löse 3x = 9", "Was nun?", True)
    assert "vorige" not in aufgabe.nutzertext("und?", "Löse 3x = 9", "Was nun?")
