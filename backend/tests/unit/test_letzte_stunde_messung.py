"""Die Prüfungen der Messung „letzte Stunde" (0.15, Todo → Chat, Punkt 2) — schlagen sie an?

Der Knoten zu XY wird gezählt; die falsche Stunde entscheidet das Lesen, das Skript markiert
Verdachtssätze. Beide müssen anschlagen, wo sie sollen, und schweigen, wo nicht.
"""
import importlib.util
from datetime import date
from pathlib import Path

_PFAD = Path(__file__).resolve().parents[2] / "scripts" / "letzte_stunde_messung.py"
_spec = importlib.util.spec_from_file_location("letzte_stunde_messung", _PFAD)
messung = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(messung)

STUNDEN = [{"begriff": "Ionenbindung"}, {"begriff": "Metallbindung"}, {"begriff": "Elektronegativität"}]
VORLETZTE = date(2026, 10, 7)
FALL_A = {"id": "a", "xy": "Elektronegativität"}


def _bewerte(antwort, vorlagen=(), fall=FALL_A):
    return messung.bewerte(fall, antwort, list(vorlagen), STUNDEN, VORLETZTE)


def test_vorletzte_als_letzte_wird_markiert():
    k = _bewerte("In der letzten Stunde (Mi 7.10.) ging es um die Metallbindung. Was ist unklar?")
    assert k["verdacht"] and k["fragt_nach"]


def test_auch_ueber_das_datum():
    assert _bewerte("Zuletzt habt ihr am 7.10. etwas über Bindungen gelernt.")["verdacht"]


def test_die_richtige_letzte_wird_nicht_markiert():
    k = _bewerte("Letzte Stunde ging es um Elektronegativität. Vorher, am 7.10., um die Metallbindung.")
    assert k["verdacht"] == []
    assert k["genannt"] == ["Metallbindung", "Elektronegativität"]


def test_der_datumspunkt_trennt_keinen_satz():
    """„am 7.10. ging es …" ist ein Satz — sonst stünden „letzte" und das Thema getrennt."""
    assert _bewerte("In der letzten Stunde am 7.10. ging es um Metallbindung.")["verdacht"]


def test_knoten_zu_xy_aus_vorab_oder_werkzeug():
    vorlagen = [{"titel": "Elektronegativität", "art": "begriff", "herkunft": "werkzeug"},
                {"titel": "Elektronegativität", "art": "begriff", "herkunft": "vorab"}]
    k = _bewerte("…", vorlagen)
    assert k["xy_knoten"] and k["xy_herkunft"] == ["vorab", "werkzeug"]


def test_ohne_knoten_oder_mit_falscher_art_fehlt_er():
    assert _bewerte("…")["xy_knoten"] is False
    assert _bewerte("…", [{"titel": "Elektronegativität", "art": "ik_kompetenz", "herkunft": "vorab"}])["xy_knoten"] is False


def test_ohne_xy_wird_nichts_gezaehlt():
    k = _bewerte("Was genau war unklar?", fall={"id": "b"})
    assert k["xy_knoten"] is None and k["fragt_nach"]


def test_termine_vor_und_nach_heute():
    # Sonntag, 11.10.2026: zurück Fr, Mi, Mo; vor Mo, Mi.
    vergangen, kommend = messung.termine([0, 2, 4], date(2026, 10, 11), 3, 2)
    assert vergangen == [date(2026, 10, 5), date(2026, 10, 7), date(2026, 10, 9)]
    assert kommend == [date(2026, 10, 12), date(2026, 10, 14)]


def test_heute_ist_weder_vergangen_noch_kommend():
    """Ein Termin heute zählte für den Block als „nächste Stunde" — die Messung legt keinen an."""
    vergangen, kommend = messung.termine([0, 2, 4], date(2026, 10, 12), 3, 2)
    assert date(2026, 10, 12) not in vergangen + kommend
