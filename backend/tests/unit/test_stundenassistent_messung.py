"""Die Kriterien der Messung zum Stundenassistenten (0.15, Schritt 6) — erkennen sie Fehlgriffe?

Eine Messung, deren Kriterien nie anschlagen, sagt „3/3 bestanden" über alles. Hier laufen
künstliche Läufe durch `bewerte`: je ein richtiger und je ein Fehlgriff pro Kriterium.
"""
import copy
import importlib.util
from pathlib import Path

import pytest

_PFAD = Path(__file__).resolve().parents[2] / "scripts" / "stundenassistent_messung.py"
_spec = importlib.util.spec_from_file_location("stundenassistent_messung", _PFAD)
messung = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(messung)

STUNDE = "s-1"
AUSGANG = {"entwuerfe": {STUNDE: {"titel": "Potenzen", "metadata": {"phasen": [
    {"id": "a", "name": "Einstieg", "dauer_min": 10},
    {"id": "b", "name": "Sicherung wird HA", "dauer_min": None},
]}}}, "slots": {}, "kanten": set()}


def _zug(werkzeuge, *, phasen=None, antwort="Soll ich das so übernehmen?", bezug=None, neu=False,
         fehler=None):
    stand = copy.deepcopy(AUSGANG)
    if phasen is not None:
        stand["entwuerfe"][STUNDE]["metadata"]["phasen"] = phasen
    if neu:
        stand["entwuerfe"]["s-neu"] = {"titel": "Neue Stunde", "metadata": {"phasen": []}}
    return {"werkzeuge": [{"tool": w} for w in werkzeuge], "stand": stand,
            "antwort": antwort, "bezug": bezug, "fehler": fehler}


FALL = {"id": "x", "stunde": {}, "zuege": ["…", "Ja"], "zustimmung_ab": 2}
GUT = [
    {"id": "a", "name": "Einstieg", "dauer_min": 10, "beschreibung": "Neu"},
    {"id": "b", "name": "Sicherung wird HA", "dauer_min": None},
    {"name": "Tafelbild", "dauer_min": 5},
]


def _bewerte(zuege, fall=FALL, **kw):
    return messung.bewerte(fall, AUSGANG, zuege, stunde=kw.pop("stunde", STUNDE), **kw)


def test_ein_guter_lauf_besteht():
    k = _bewerte([_zug(["get_lesson_detail"]), _zug(["update_lesson_phases"], phasen=GUT)])
    assert all(k.values()), k
    assert set(k) == {"antwort_nicht_leer", "zuerst_gelesen", "nicht_ohne_zustimmung",
                      "schreibt_nach_zustimmung", "kennungen_erhalten", "skizze_ohne_dauer"}


@pytest.mark.parametrize("zuege,kriterium", [
    # nicht zuerst gelesen
    ([_zug(["search_context_nodes", "get_lesson_detail"]), _zug(["update_lesson_phases"], phasen=GUT)],
     "zuerst_gelesen"),
    ([_zug([]), _zug(["update_lesson_phases"], phasen=GUT)], "zuerst_gelesen"),
    # vor der Zustimmung geschrieben — am Werkzeug und am Stand
    ([_zug(["get_lesson_detail", "update_lesson_phases"], phasen=GUT), _zug([], phasen=GUT)],
     "nicht_ohne_zustimmung"),
    # einen Entwurf angelegt
    ([_zug(["get_lesson_detail"], neu=True), _zug(["update_lesson_phases"], phasen=GUT)],
     "nicht_ohne_zustimmung"),
    # nach der Zustimmung nicht geschrieben
    ([_zug(["get_lesson_detail"]), _zug(["get_lesson_detail"])], "schreibt_nach_zustimmung"),
    # Kennungen verloren: alles neu
    ([_zug(["get_lesson_detail"]), _zug(["update_lesson_phases"], phasen=[
        {"name": "Einstieg", "dauer_min": 10}, {"name": "Sicherung wird HA", "dauer_min": None}])],
     "kennungen_erhalten"),
    # … oder nur eine Phase, gleichnamig neu geschrieben
    ([_zug(["get_lesson_detail"]), _zug(["update_lesson_phases"], phasen=[
        {"id": "a", "name": "Einstieg", "dauer_min": 10}, {"name": "Sicherung wird HA:", "dauer_min": None}])],
     "kennungen_erhalten"),
    # leere Antwort — oder ein Zug, der mit einem Abbruch endete
    ([_zug(["get_lesson_detail"], antwort="  "), _zug(["update_lesson_phases"], phasen=GUT)],
     "antwort_nicht_leer"),
    ([_zug(["get_lesson_detail"]), _zug(["update_lesson_phases"], phasen=GUT, fehler="Der KI-Dienst …")],
     "antwort_nicht_leer"),
    # Minuten für die Skizze erfunden
    ([_zug(["get_lesson_detail"]), _zug(["update_lesson_phases"], phasen=[
        {"id": "a", "name": "Einstieg", "dauer_min": 10}, {"id": "b", "name": "Sicherung wird HA", "dauer_min": 5}])],
     "skizze_ohne_dauer"),
])
def test_fehlgriffe_werden_erkannt(zuege, kriterium):
    assert _bewerte(zuege)[kriterium] is False


def test_zusammenlegen_ist_kein_verlust():
    """D1: Eine zusammengelegte Phase heißt neu — das ist gewollt, kein Verlust. Bis Messung 3
    zählte jede neue Kennung und schlug genau hier an."""
    k = _bewerte([_zug(["get_lesson_detail"]), _zug(["update_lesson_phases"], phasen=[
        {"name": "Einstieg & Sicherung", "dauer_min": 10}])])
    assert k["kennungen_erhalten"] is True


def test_ohne_bezug_waehlen_und_nachfragen():
    fall_waehlt = {"id": "w", "zuege": ["…"], "waehlt": {}}
    gut = _bewerte([_zug(["finde_stunde", "waehle_stunde"], bezug="ziel")], fall_waehlt, stunde=None, ziel="ziel")
    assert gut == {"antwort_nicht_leer": True, "zuerst_gelesen": True, "nicht_ohne_zustimmung": True,
                   "waehlt_den_termin": True}
    falsch = _bewerte([_zug(["finde_stunde", "waehle_stunde"], bezug="anderer")], fall_waehlt,
                      stunde=None, ziel="ziel")
    assert falsch["waehlt_den_termin"] is False

    fall_frage = {"id": "f", "zuege": ["…"], "nachfrage": True}
    assert _bewerte([_zug(["finde_stunde"], antwort="Welche meinst du?")], fall_frage, stunde=None)["fragt_nach"]
    # selbst gewählt statt gefragt
    assert not _bewerte([_zug(["finde_stunde", "waehle_stunde"], bezug="x")], fall_frage, stunde=None)["fragt_nach"]
    # Den Wortlaut beurteilt Jan im Verlauf (D1) — ein fehlendes Fragezeichen zählt nicht mehr.
    assert _bewerte([_zug(["finde_stunde"], antwort="Ich habe nichts gefunden.")], fall_frage,
                    stunde=None)["fragt_nach"]


# ── Kompetenzen (D2) ─────────────────────────────────────────────────────────

FALL_K = {"id": "k", "stunde": {}, "zuege": ["…"], "kompetenzen": {"praefixe": ["3.4.", "2."]}}
BEKANNT = {"3.4.5(4)", "3.4.5(2)", "2.3.11", "3.2.1.1(3)", "3.3.2(3)"}
GUTE_ANTWORT = ("Nach dem Bildungsplan 2016: **3.4.5 (4)** Mechanismen beschreiben, 3.4.5(2) "
                "Gesundheitsgefährdung, dazu 2.3.11. Am 13.10.2026 geht es weiter (Leitidee 3.4.5).")
KRITERIEN_K = ("kompetenz_aus_quelle", "kompetenzen_genannt", "kompetenzen_der_stufe", "kein_fremder_plan")


def _k(antwort, werkzeuge=("get_lesson_detail", "search_context_nodes"), **kw):
    return _bewerte([_zug(list(werkzeuge), antwort=antwort)], FALL_K, nummern=BEKANNT, **kw)


def test_kompetenznummern_aus_dem_text():
    """Mit und ohne Leerzeichen vor der Klammer, prozessbezogen ohne Klammer — aber kein Datum
    und keine bloße Abschnittsnummer."""
    assert messung.kompetenznummern(GUTE_ANTWORT) == ["3.4.5(4)", "3.4.5(2)", "2.3.11"]
    assert messung.kompetenznummern("3.4.5 (4) und 2.1(1)") == ["3.4.5(4)", "2.1(1)"]


def test_eine_gute_kompetenzantwort_besteht():
    k = _k(GUTE_ANTWORT)
    assert all(k[n] for n in KRITERIEN_K), k
    # Das Kapitel der Einheit ist auch eine Quelle (A1) — dann muss nicht gesucht werden.
    assert _k(GUTE_ANTWORT, werkzeuge=("get_lesson_detail",), kapitel=True)["kompetenz_aus_quelle"]


@pytest.mark.parametrize("antwort,werkzeuge,kriterium", [
    (GUTE_ANTWORT, ("get_lesson_detail",), "kompetenz_aus_quelle"),            # aus dem Gedächtnis
    ("Die Stunde fördert Fachwissen und Kommunikation.", None, "kompetenzen_genannt"),
    (GUTE_ANTWORT + " Außerdem 3.2.1.1(3).", None, "kompetenzen_der_stufe"),   # Mittelstufe
    (GUTE_ANTWORT + " Außerdem 3.3.2(3).", None, "kompetenzen_der_stufe"),     # Basisfach
    (GUTE_ANTWORT + " Außerdem 3.4.9(7).", None, "kompetenzen_der_stufe"),     # erfunden
    (GUTE_ANTWORT + " Laut österreichischem Lehrplan …", None, "kein_fremder_plan"),
])
def test_kompetenz_fehlgriffe_werden_erkannt(antwort, werkzeuge, kriterium):
    k = _k(antwort, werkzeuge) if werkzeuge else _k(antwort)
    assert k[kriterium] is False


# ── Verlauf: vollständige Beschreibungen (D7), Erwartung und Bewertung (D5) ──

def _verlauf(**lauf):
    basis = {"fall": "x", "lauf": 1, "bestanden": True, "kriterien": {}, "zuege": []}
    kopf = {"datei": "t.yaml", "beginn": "heute", "modell": "m", "assistent_name": "A",
            "assistent": 1, "prompt": "p"}
    return messung.verlauf_als_markdown(kopf, [{**basis, **lauf}])


def test_der_verlauf_kuerzt_keine_beschreibung():
    lang = "Zeile eins mit viel Text " * 6 + "\nund eine zweite Zeile, die bis Messung 3 fehlte"
    text = _verlauf(vorher=[{"name": "A"}], nachher=[{"name": "A", "beschreibung": lang}])
    assert "und eine zweite Zeile, die bis Messung 3 fehlte" in text


def test_erwartung_und_kaestchen_und_auszaehlung():
    text = _verlauf(erwartung="Nennt die Phasen einzeln.")
    assert "Nennt die Phasen einzeln." in text
    assert all(f"- [ ] {b}" in text for b in messung.BEWERTUNGEN)
    zwei = text + text.replace("## x · Lauf 1", "## x · Lauf 2")
    angekreuzt = zwei.replace("- [ ] teilweise", "- [x] teilweise", 1)
    assert messung.bewertungen(angekreuzt)["x"] == {"teilweise": 1, "offen": 1}
    doppelt = text.replace("- [ ] brauchbar", "- [x] brauchbar").replace("- [ ] unbrauchbar", "- [x] unbrauchbar")
    assert messung.bewertungen(doppelt)["x"] == {"mehrdeutig": 1}


def test_ohne_erwartung_keine_kaestchen():
    assert "**Bewertung:**" not in _verlauf()


def test_die_szenarien_tragen_erwartungen():
    """D5: Ohne Erwartung gibt es nichts anzukreuzen — und die Abnahme schließt die Bewertung ein."""
    import yaml
    for datei in ("stundenentwurf.yaml", "stunde_finden.yaml"):
        faelle = yaml.safe_load((_PFAD.parent / "szenarien" / datei).read_text(encoding="utf-8"))["faelle"]
        assert all(f.get("erwartung", "").strip() for f in faelle), datei
        assert not any("neue_phasen_hoechstens" in f for f in faelle), "seit D1 ohne Wirkung"


# ── Kompetenzen aus dem Kapitel (A4) ─────────────────────────────────────────

FALL_KAP = {"id": "kap", "stunde": {}, "zuege": ["…"],
            "kompetenzen": {"praefixe": ["3.4.", "2."], "kapitel": True}}
KAPITEL = {"3.4.5(1)", "3.4.5(2)", "3.4.5(3)", "3.4.5(4)", "3.4.5(5)"}
BEKANNT_K = KAPITEL | {"3.4.1(6)", "2.3.11"}


def _kap(antwort):
    return _bewerte([_zug(["get_lesson_detail"], antwort=antwort)], FALL_KAP, nummern=BEKANNT_K,
                    kapitel=True, kapitel_nummern=KAPITEL)


def test_kompetenzen_aus_dem_kapitel():
    k = _kap("Aus dem Kapitel: 3.4.5(4) Mechanismus, 3.4.5(2) Gefährdung; dazu 2.3.11.")
    assert k["kompetenzen_aus_dem_kapitel"] and k["kompetenz_aus_quelle"], k


@pytest.mark.parametrize("antwort", [
    "3.4.5(4) Mechanismus und 3.4.1(6) Entropie.",      # späteres Thema derselben Stufe
    "Prozessbezogen: 2.3.11.",                          # keine einzige aus dem Kapitel
])
def test_kapitel_fehlgriffe_werden_erkannt(antwort):
    k = _kap(antwort)
    assert k["kompetenzen_aus_dem_kapitel"] is False
    if "3.4.1(6)" in antwort:
        assert k["kompetenzen_der_stufe"], "die Präfixe allein sähen es nicht — deshalb das Kriterium"


def test_aufbau_wird_vorher_geprueft():
    assert messung.aufbau_fehler(FALL_KAP, kapitel=True) is None
    assert "braucht" in messung.aufbau_fehler(FALL_KAP, kapitel=False)
    ohne = {**FALL_KAP, "kompetenzen": {"praefixe": ["3.4."], "kapitel": False}}
    assert "darf kein" in messung.aufbau_fehler(ohne, kapitel=True)
    assert messung.aufbau_fehler({"id": "x"}, kapitel=True) is None


def test_notizen_unter_der_bewertung():
    """Die Notiz steht in der Regel eine Leerzeile unter „Notiz:" — so übersah eine Suche
    nur nach derselben Zeile alle Notizen von Messung 4."""
    text = _verlauf(erwartung="E.")
    darunter = text.replace("Notiz: \n", "Notiz: \n\nDie Phase ist eine Sicherung,\naber nicht so benannt.\n")
    assert messung.notizen(darunter) == [("x · Lauf 1", "Die Phase ist eine Sicherung, aber nicht so benannt.")]
    assert messung.notizen(text.replace("Notiz: ", "Notiz: gleich daneben")) == [("x · Lauf 1", "gleich daneben")]
    assert messung.notizen(text) == []
