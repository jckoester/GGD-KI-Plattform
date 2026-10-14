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
    bekannt. Ob die Fachgrenzen zu den Bezugsfächern passen, prüft das Skript gegen die
    Instanz (`bezug_abweichungen`)."""
    daten = yaml.safe_load((_SKRIPTE / "szenarien" / "vorab_begriffe.yaml").read_text(encoding="utf-8"))
    assert len(daten["rahmen"]) == 4 and all("{akk}" in r for r in daten["rahmen"])
    arten = {"einwort", "gebeugt", "kompositum", "mehrwort", "plural_titel", "alias", "stoffsteckbrief",
             "mehrdeutig"}
    for fach, eintraege in daten["begriffe"].items():
        assert 8 <= len(eintraege) <= 10, fach
        assert {e["art"] for e in eintraege} <= arten, fach
    assert "bezugsfaecher" not in daten, "Bezugsfächer gehören nach config/subjects.yaml"


# ── Bezugsfächer der Instanz gegen das Szenario ──────────────────────────────

GRENZFAELLE = {
    "rahmen": MINI["rahmen"], "ich": MINI["ich"], "begriffe": {}, "gegenproben": {
        "beilaeufig": {"faecher": [], "saetze": []}, "schulnah": {"faecher": [], "saetze": []},
        "alltag": [], "anderes_fach": []},
    "fachgrenzen": [
        {"chat": "nwt", "fach": "biologie", "titel": "Fotosynthese", "art": "einwort",
         "stichwort": "Fotosynthese", "frage": "Was ist Fotosynthese?", "akk": "die Fotosynthese"},
        {"chat": "mathematik", "fach": "nwt", "titel": "Standardabweichung", "art": "einwort",
         "bezug": False, "stichwort": "Standardabweichung", "frage": "Was ist sie?", "akk": "sie"},
    ],
}


def test_passende_bezugsfaecher_ergeben_keine_abweichung():
    liste = M.nachrichten(GRENZFAELLE)
    assert M.bezug_abweichungen(liste, {"nwt": ["biologie", "chemie"]}) == []


def test_fehlendes_bezugsfach_faellt_auf_einmal_je_fall():
    """NwT ohne Biologie: Der Fall „mit Bezug" stimmt nicht mehr — einmal gemeldet, nicht
    je Form (sieben Nachrichten)."""
    abweichend = M.bezug_abweichungen(M.nachrichten(GRENZFAELLE), {"nwt": ["chemie"]})
    assert len(abweichend) == 1 and "Fotosynthese" in abweichend[0]


def test_unerwarteter_bezug_faellt_auf():
    """Gegenrichtung: Hat Mathematik doch NwT als Bezugsfach, ist der Grenzfall keiner mehr."""
    abweichend = M.bezug_abweichungen(M.nachrichten(GRENZFAELLE),
                                      {"nwt": ["biologie"], "mathematik": ["nwt"]})
    assert len(abweichend) == 1 and "Standardabweichung" in abweichend[0]


# ── Tor-Raster und Wahl der Tore (Schritt 3) ─────────────────────────────────

ALKAN = M.Nachricht("Erzählsatz zu Alkanen", "fachlich", "erzaehlung", (None, "chemie"), ("chemie", "Alkane"),
                    rahmen=1)


def _raster(n, je_tor, profil=None):
    """``je_tor``: Treffer je Tor-Paar; fehlende Paare = wie „Nennung aus"."""
    aus = je_tor.get(M.TOR_AUS, [])
    return {"nachricht": n, "profil": profil, "raster": {k: je_tor.get(k, aus) for k in M.TOR_RASTER}}


def test_raster_zaehlt_neue_fehltreffer_gegen_nennung_aus():
    w, u = T("Wasser", "chemie", "nennung", 0.49), T("Umwelt (GHS09)", "chemie", "nennung", 0.47)
    lauf = _raster(EIS, {M.TOR_AUS: [w], (0.55, 0.50): [w, u]})
    assert M.raster_zeile([lauf], M.TOR_AUS)["fehltreffer_neu"] == 0
    z = M.raster_zeile([lauf], (0.55, 0.50))
    assert z["fehltreffer_neu"] == 1 and z["gegenproben_neu"] == [1, 1]


def test_raster_zaehlt_erzaehlsaetze_und_neue_nebentreffer():
    alk = T("Alkane", "chemie", "nennung", 0.52)
    alkine = T("Alkine", "chemie", "distanz", 0.44)
    lauf = _raster(ALKAN, {M.TOR_AUS: [alkine], (0.55, None): [alk, alkine]})
    z = M.raster_zeile([lauf], (0.55, None))
    assert z["formen"]["erzaehlung"] == [1, 1] and z["nebentreffer_neu"] == 0


def test_wahl_schliesst_jeden_neuen_fehltreffer_aus():
    """Das weitere Tor fände mehr Erzählsätze — aber es brächte einen Fehltreffer."""
    alk = T("Alkane", "chemie", "nennung", 0.57)
    eis = T("Wasser", "chemie", "nennung", 0.57)
    laeufe = [_raster(ALKAN, {(0.58, a): [alk] for a in (None, 0.46, 0.48, 0.50, 0.52)}),
              _raster(EIS, {(0.58, a): [eis] for a in (None, 0.46, 0.48, 0.50, 0.52)})]
    assert M.tore_waehlen(laeufe) == (0.50, None)     # alle anderen gleich gut → die engste


def test_wahl_nimmt_die_meisten_erzaehlsaetze_dann_die_engere():
    alk = T("Alkane", "chemie", "nennung", 0.53)
    ab_054 = {(t, a): [alk] for t in (0.54, 0.55, 0.56, 0.58) for a in (None, 0.46, 0.48, 0.50, 0.52)}
    assert M.tore_waehlen([_raster(ALKAN, ab_054)]) == (0.54, None)


def test_keine_zulaessige_kombination():
    eis = T("Wasser", "chemie", "nennung", 0.40)
    alle = {k: [eis] for k in M.TOR_RASTER if k != M.TOR_AUS}
    assert M.tore_waehlen([_raster(EIS, alle)]) is None


def test_raster_ohne_jede_wirkung_faellt_auf():
    gleich = _raster(ALKAN, {M.TOR_AUS: []})
    assert M.raster_wirkungslos([gleich])
    anders = _raster(ALKAN, {(0.58, 0.52): [T("Alkane", "chemie", "nennung", 0.57)]})
    assert not M.raster_wirkungslos([gleich, anders])


# ── Zweite Gegenprobenreihe (Format, nicht Inhalt) ───────────────────────────


def test_zweite_reihe_mit_alltag_und_eigenen_erzaehlsaetzen():
    daten = {"alltag": [{"fach": "chemie", "wort": "Eis", "satz": "Ein Eis, bitte."}],
             "erzaehlsaetze": [{"fach": "mathematik", "titel": "Mitternachtsformel",
                                "satz": "Mein Nachhilfelehrer meinte, ich soll die Mitternachtsformel nehmen."}]}
    liste = M.nachrichten(daten)
    eis = next(n for n in liste if n.art == "gegenprobe")
    erz = next(n for n in liste if n.art == "fachlich")
    assert (eis.form, eis.faecher, eis.wort) == ("alltag", (None, "chemie"), "Eis")
    assert (erz.form, erz.faecher, erz.erwartet) == ("erzaehlung", (None, "mathematik"),
                                                     ("mathematik", "Mitternachtsformel"))


def test_unbekannter_schluessel_bricht_ab():
    import pytest
    with pytest.raises(SystemExit):
        M.nachrichten({"alltags": []})


def test_fehlerhafte_eintraege_werden_alle_genannt():
    """Ein Tippfehler („title" statt „titel") oder ein leerer Satz — alle auf einmal, mit Nummer."""
    daten = {"erzaehlsaetze": [{"fach": "chemie", "titel": "Ion", "satz": "Ich verstehe Ionen nicht."},
                               {"fach": "chemie", "title": "Oxidation", "satz": "Was ist das?"}],
             "alltag": [{"fach": "chemie", "wort": "", "satz": ""}]}
    fehler = M.eintraege_pruefen(daten)
    assert fehler == ["erzaehlsaetze Nr. 2: unbekanntes Feld „title“",
                      "erzaehlsaetze Nr. 2: „titel“ fehlt oder ist leer",
                      "alltag Nr. 1: „satz“ fehlt oder ist leer"]


def test_wort_darf_leer_sein():
    """`wort` dient nur dem Lesen — ein Alltagssatz ohne ist vollständig."""
    assert M.eintraege_pruefen({"alltag": [{"fach": "chemie", "wort": None, "satz": "Ein Satz."}]}) == []


def test_eigener_erzaehlsatz_ueber_fachgrenzen_und_mit_alternativen():
    daten = {"erzaehlsaetze": [
        {"fach": "mathematik", "chat": "nwt", "titel": "Median", "satz": "Der Median ist robust, warum?"},
        {"fach": "mathematik", "titel": "n-te Wurzel", "auch": ["Wurzelziehen"],
         "satz": "Warum darf man aus negativen Zahlen keine Wurzel ziehen?"}]}
    median, wurzel = M.nachrichten(daten)
    assert (median.art, median.faecher, median.erwartet, median.bezug) == (
        "fachgrenze", ("nwt",), ("mathematik", "Median"), True)
    assert wurzel.art == "fachlich" and wurzel.faecher == (None, "mathematik")
    assert M.gefunden(wurzel, [T("Wurzelziehen", "mathematik", "nennung", 0.48)])
    assert M.gefunden(wurzel, [T("n-te Wurzel", "mathematik", "distanz", 0.40)])
    assert not M.gefunden(wurzel, [T("Wurzelziehen", "chemie", "nennung", 0.48)])
    assert not M.gefunden(wurzel, [T("Potenz", "mathematik", "distanz", 0.40)])
