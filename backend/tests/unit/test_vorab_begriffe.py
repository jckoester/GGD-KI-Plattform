"""Die Auswertung des Prüfsatzes „Begriff im Satz" (0.16, Schritt 1) — schlägt sie an?

Gegenproben zählen **jeden** Treffer, nicht nur den nächsten; der erwartete Knoten zählt
unter allen Treffern, nicht nur auf Platz 1; über Fachgrenzen zählt nur, was weder aus dem
Chat-Fach noch aus einem Bezugsfach stammt.
"""
import importlib.util
from pathlib import Path

import yaml

_SKRIPTE = Path(__file__).resolve().parents[2] / "scripts"
_spec = importlib.util.spec_from_file_location("vorab_begriffe", _SKRIPTE / "vorab_begriffe.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

T = M.Treffer
ION = M.Nachricht("Ich verstehe Ionen nicht.", "fachlich", "ich", (None, "chemie"), ("chemie", "Ion"), "mehrdeutig")
EIS = M.Nachricht("Wir wollen nachher ein Eis essen.", "gegenprobe", "alltag", (None, "chemie"), wort="Eis")
BEZUG = {"nwt": ["biologie", "chemie"]}


def _lauf(n, treffer_je_schwelle, profil=None):
    return {"nachricht": n, "profil": profil, "treffer": treffer_je_schwelle}


# ── Gegenproben: jeder Treffer, nicht nur der nächste ────────────────────────


def test_gegenprobe_zaehlt_jeden_treffer():
    """Mit Fachbonus steht vorn nicht unbedingt der rohe nächste Treffer — eine Auswertung,
    die nur den ersten ansieht, übersähe den zweiten."""
    treffer = [T("Wasser", "chemie", "distanz", 0.44), T("Umwelt (GHS09)", "chemie", "distanz", 0.43)]
    assert M.fehltreffer(EIS, treffer) == treffer


def test_gegenprobe_mit_fehltreffer_nur_auf_platz_zwei_wird_gezaehlt():
    lauf = _lauf(EIS, {0.45: [T("Wasser", "chemie", "distanz", 0.44),
                              T("Gemisch", "chemie", "distanz", 0.45),
                              T("Stoffe", "chemie", "distanz", 0.45)]})
    z = M.zaehle([lauf], 0.45, BEZUG)
    assert z["gegenproben"] == [1, 1]
    assert z["fehltreffer"] == 3


def test_fachliche_nachricht_hat_keine_fehltreffer():
    assert M.fehltreffer(ION, [T("Ionenbindung", "chemie", "distanz", 0.40)]) == []


# ── Erwarteter Knoten: unter allen Treffern, Fach und Titel ──────────────────


def test_erwarteter_knoten_zaehlt_auch_auf_platz_drei():
    treffer = [T("Ionenbindung", "chemie", "distanz", 0.38), T("Ionengitter", "chemie", "distanz", 0.40),
               T("Ion", "chemie", "distanz", 0.42)]
    assert M.gefunden(ION, treffer) == treffer[2]
    assert M.nebentreffer(ION, treffer) == treffer[:2]


def test_gleicher_titel_aus_anderem_fach_ist_nicht_der_erwartete():
    treffer = [T("Ion", "nwt", "name", None)]
    assert M.gefunden(ION, treffer) is None
    assert M.nebentreffer(ION, treffer) == treffer


def test_zaehlung_je_form():
    stich = M.Nachricht("Ion", "fachlich", "stichwort", (None, "chemie"), ("chemie", "Ion"))
    erz = M.Nachricht("Letzte Stunde … Ionen …", "fachlich", "erzaehlung", (None, "chemie"), ("chemie", "Ion"),
                      rahmen=1)
    laeufe = [_lauf(stich, {0.45: [T("Ion", "chemie", "name", 0.3)]}),
              _lauf(erz, {0.45: []})]
    z = M.zaehle(laeufe, 0.45, BEZUG)
    assert z["formen"]["stichwort"] == [1, 1]
    assert z["formen"]["erzaehlung"] == [0, 1]


# ── Über Fachgrenzen ─────────────────────────────────────────────────────────


def test_ohne_bezug_nennt_nur_faecher_ausserhalb_von_chat_und_bezug():
    treffer = [T("Fotosynthese", "biologie", "distanz", 0.40), T("Median", "mathematik", "distanz", 0.41),
               T("Gedichtanalyse", None, "distanz", 0.42), T("Stoffstrom", "nwt", "distanz", 0.43)]
    assert M.ohne_bezug("nwt", treffer, BEZUG) == [treffer[1]]


def test_ohne_fach_im_profil_gibt_es_kein_ohne_bezug():
    assert M.ohne_bezug(None, [T("Median", "mathematik", "distanz", 0.41)], BEZUG) == []


def test_fachgrenze_ohne_bezug_zaehlt_nicht_zum_kriterium():
    mit = M.Nachricht("Was ist Fotosynthese?", "fachgrenze", "frage", ("nwt",), ("biologie", "Fotosynthese"))
    ohne = M.Nachricht("Was ist die Standardabweichung?", "fachgrenze", "frage", ("mathematik",),
                       ("nwt", "Standardabweichung"), bezug=False)
    laeufe = [_lauf(mit, {0.45: []}, "nwt"), _lauf(ohne, {0.45: []}, "mathematik")]
    assert M.zaehle(laeufe, 0.45, BEZUG)["fachgrenze"] == [0, 1]


# ── Abtastung ────────────────────────────────────────────────────────────────


def test_neu_hinzu_nennt_nur_was_dazukommt_und_seine_rolle():
    w, u = T("Wasser", "chemie", "distanz", 0.44), T("Umwelt (GHS09)", "chemie", "distanz", 0.455)
    i, b = T("Ion", "chemie", "distanz", 0.452), T("Ionenbindung", "chemie", "distanz", 0.459)
    laeufe = [_lauf(EIS, {0.45: [w], 0.46: [w, u]}), _lauf(ION, {0.45: [], 0.46: [i, b]})]
    neu = [(l["nachricht"].text, t.titel, r) for l, t, r in M.neu_hinzu(laeufe, 0.45, 0.46)]
    assert neu == [(EIS.text, "Umwelt (GHS09)", "Fehltreffer"),
                   (ION.text, "Ion", "erwartet"), (ION.text, "Ionenbindung", "Nebentreffer")]


def test_abtastung_ohne_jede_aenderung_gilt_als_wirkungslos():
    gleich = {s: [T("Ion", "chemie", "name", 0.3)] for s in M.SCHWELLEN}
    assert M.abtastung_wirkungslos([_lauf(ION, gleich)])
    anders = dict(gleich)
    anders[M.SCHWELLEN[-1]] = [*gleich[M.SCHWELLEN[0]], T("Ionengitter", "chemie", "distanz", 0.51)]
    assert not M.abtastung_wirkungslos([_lauf(ION, gleich), _lauf(ION, anders)])


def test_schwellen_von_040_bis_052():
    assert M.SCHWELLEN[0] == 0.40 and M.SCHWELLEN[-1] == 0.52 and len(M.SCHWELLEN) == 13
    assert 0.45 in M.SCHWELLEN


# ── Szenario ─────────────────────────────────────────────────────────────────

MINI = {
    "stufe": 10,
    "rahmen": ["A {akk} a.", "B {akk} b.", "C {akk} c.", "D {akk} d."],
    "ich": "Ich verstehe {akk} nicht.",
    "begriffe": {"chemie": [
        {"titel": "Ion", "art": "mehrdeutig", "stichwort": "Ion", "frage": "Was ist ein Ion?", "akk": "Ionen"},
        {"titel": "Gütekriterien", "art": "plural_titel", "stichwort": "Gütekriterium",
         "frage": "Was ist ein Gütekriterium?", "akk": "ein Gütekriterium", "ich": "Eigener Ich-Satz."},
    ]},
    "gegenproben": {"beilaeufig": {"faecher": ["chemie"], "saetze": ["Danke!"]},
                    "schulnah": {"faecher": ["chemie", "nwt"], "saetze": ["S1", "S2"]},
                    "alltag": [{"fach": "chemie", "wort": "Eis", "satz": "Ein Eis."}],
                    "anderes_fach": [{"fach": "deutsch", "wort": "Endung", "satz": "Endung?"}]},
}


def test_jeder_begriff_in_vier_formen_und_jedem_rahmen():
    ion = [n for n in M.nachrichten(MINI) if n.erwartet == ("chemie", "Ion")]
    assert [n.text for n in ion] == ["Ion", "Was ist ein Ion?", "Ich verstehe Ionen nicht.",
                                     "A Ionen a.", "B Ionen b.", "C Ionen c.", "D Ionen d."]
    assert all(n.faecher == (None, "chemie") for n in ion)


def test_eigener_ich_satz_ersetzt_die_vorlage():
    gk = [n for n in M.nachrichten(MINI) if n.erwartet == ("chemie", "Gütekriterien") and n.form == "ich"]
    assert [n.text for n in gk] == ["Eigener Ich-Satz."]


def test_im_test_chat_je_begriff_ein_erzaehlsatz_rahmen_reihum():
    im_chat = [(n.erwartet[1], n.rahmen) for n in M.nachrichten(MINI) if n.chat and n.erwartet]
    assert im_chat == [("Ion", 1), ("Gütekriterien", 2)]


def test_gegenproben_profile_und_chats():
    proben = {n.text: n for n in M.nachrichten(MINI) if n.art == "gegenprobe"}
    assert proben["Danke!"].faecher == (None, "chemie") and proben["Danke!"].chat is None
    assert (proben["S1"].chat, proben["S2"].chat) == ("chemie", "nwt")
    assert proben["Ein Eis."].faecher == (None, "chemie")
    assert proben["Endung?"].faecher == ("deutsch",)


def test_szenariodatei_ist_vollstaendig():
    """Die echte Datei: jeder Rahmen setzt den Begriff ein, je Fach 8–10 Begriffe, jede Art
    bekannt, und jedes Fach der Fachgrenzen hat seine Bezugsfächer eingetragen."""
    daten = yaml.safe_load((_SKRIPTE / "szenarien" / "vorab_begriffe.yaml").read_text(encoding="utf-8"))
    assert len(daten["rahmen"]) == 4 and all("{akk}" in r for r in daten["rahmen"])
    arten = {"einwort", "gebeugt", "kompositum", "mehrwort", "plural_titel", "alias", "stoffsteckbrief",
             "mehrdeutig"}
    for fach, eintraege in daten["begriffe"].items():
        assert 8 <= len(eintraege) <= 10, fach
        assert {e["art"] for e in eintraege} <= arten, fach
    for e in daten["fachgrenzen"]:
        assert (e["fach"] in daten["bezugsfaecher"].get(e["chat"], [])) == e.get("bezug", True), e["titel"]
