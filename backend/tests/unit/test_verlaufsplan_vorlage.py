"""Vorschau „Einheiten aus dem Jahresverlaufsplan“ (BD Teil B, Schritt 3): ohne Datenbank."""
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from app.planning.verlaufsplan_vorlage import (
    BELEGT, KAPITEL_VORHANDEN, NACH_SCHULJAHRESENDE, PUFFER, SCHON_ANGELEGT, VORBEI, vorschau,
)

# Vier Unterrichtswochen: 06.10., 13.10., dann Herbstferien, 27.10., 03.11.
LAGE = {
    "wochen": [{"nr": 1, "montag": "2025-10-06"}, {"nr": 2, "montag": "2025-10-13"},
               {"nr": 3, "montag": "2025-10-27"}, {"nr": 4, "montag": "2025-11-03"}],
    "abschnitte": [{"von_woche": 1, "bis_woche": 2}, {"von_woche": 3, "bis_woche": 3},
                   {"von_woche": 4, "bis_woche": 4}, {"von_woche": 5, "bis_woche": 6}],
}
TITEL = {"k1": "Ähnlichkeit", "k2": "Pythagoras", "k3": "Altes Kapitel", "s1": "Strahlensätze", "s2": "Streckung"}


def _slot(tag, kategorie="unterricht", ue=None, stunde=None, pinned=False, periode=1):
    return SimpleNamespace(id=uuid4(), date=tag, start_period=periode, kategorie=kategorie,
                           ue_node_id=ue, stunde_node_id=stunde, pinned=pinned)


def _slots():
    # Je Woche Mo und Do
    tage = [date(2025, 10, 6), date(2025, 10, 9), date(2025, 10, 13), date(2025, 10, 16),
            date(2025, 10, 27), date(2025, 10, 30), date(2025, 11, 3), date(2025, 11, 6)]
    return [_slot(t) for t in tage]


def _lauf(abschnitte, *, slots=None, planungsart="kapitel", heute=date(2025, 10, 1), **kw):
    args = dict(kapitel_von={"s1": "k1", "s2": "k1"}, titel=TITEL, kapitel_aktiv={"k1", "k2"},
                kapitel_mit_einheit=set(), angelegte_abschnitte=set())
    args.update(kw)
    return vorschau(abschnitte, LAGE, planungsart=planungsart, slots=_slots() if slots is None else slots,
                    heute=heute, **args)


def _abschnitte():
    return [
        {"id": "a1", "titel": "", "kapitel_ids": ["k1", "k2"], "notiz": "mit GeoGebra"},
        {"id": "a2", "titel": "Puffer", "puffer": True},
        {"id": "a3", "titel": "Projekt", "kapitel_ids": []},
        {"id": "a4", "titel": "Nach dem Ende", "kapitel_ids": ["k2"]},
    ]


def test_je_abschnitt_eine_einheit_puffer_ohne():
    a, p, proj, ende = _lauf(_abschnitte())
    assert (a.anlegen, a.titel, a.kapitel_id, a.wochen) == (True, "Ähnlichkeit", "k1", "Woche 1–2")
    assert a.stunden == 4
    assert a.beschreibung.splitlines() == [
        "Aus dem Jahresverlaufsplan der Fachschaft: Abschnitt 1, Woche 1–2.",
        "Weitere Kapitel: Pythagoras", "Notiz: mit GeoGebra"]
    assert (p.anlegen, p.grund, p.slot_ids) == (False, PUFFER, [])
    # Ohne Kapitel: trotzdem eine Einheit, mit den Terminen von Woche 4
    assert (proj.anlegen, proj.titel, proj.kapitel_id, proj.stunden) == (True, "Projekt", None, 2)
    # Ganz hinter dem Schuljahresende: keine Woche, keine Einheit
    assert (ende.anlegen, ende.grund) == (False, NACH_SCHULJAHRESENDE)


def test_sequenzgenau_kapitel_der_ersten_sequenz():
    (v,) = _lauf([{"id": "a1", "titel": "Strahlen", "sequenz_ids": ["s2", "s1"]}], planungsart="sequenz")
    assert (v.kapitel_id, v.titel) == ("k1", "Strahlen")
    assert "Lernsequenzen: Streckung, Strahlensätze" in v.beschreibung
    assert "Kapitel" not in v.beschreibung.split("\n", 1)[1]


def test_nur_freie_unterrichtstermine():
    s = _slots()
    s[0].kategorie = "pruefung"
    s[1].ue_node_id = uuid4()
    s[2].stunde_node_id = uuid4()
    s[3].pinned = True
    (v,) = _lauf([{"id": "a1", "titel": "x", "kapitel_ids": ["k1"]}], slots=s)
    assert v.slot_ids == [] and v.belegt == 3   # die Prüfung zählt nicht als belegter Unterricht
    s[3].pinned = False
    s[3].thema = "Wiederholung"                 # freier Text hindert nicht
    (v,) = _lauf([{"id": "a1", "titel": "x", "kapitel_ids": ["k1"]}], slots=s)
    assert v.slot_ids == [s[3].id]


def test_nichts_ueberschreiben_und_nicht_doppelt():
    a, _, proj, _ = _lauf(_abschnitte(), kapitel_mit_einheit={"k1"}, angelegte_abschnitte={"a3"})
    assert (a.anlegen, a.grund, a.slot_ids) == (False, KAPITEL_VORHANDEN, [])
    assert (proj.anlegen, proj.grund) == (False, SCHON_ANGELEGT)


def test_vergangenes_wird_nicht_belegt():
    # Heute ist Do der Woche 2: Woche 1 ist vorbei, in Woche 2 nur noch der Donnerstag
    a, _, proj, _ = _lauf(_abschnitte(), heute=date(2025, 10, 16))
    assert a.anlegen and [s for s in a.slot_ids] and a.stunden == 1
    v = _lauf([{"id": "a1", "titel": "x", "kapitel_ids": ["k1"]}], heute=date(2025, 10, 20))[0]
    assert (v.anlegen, v.grund) == (False, VORBEI)


def test_kapitel_nicht_mehr_veroeffentlicht():
    (v,) = _lauf([{"id": "a1", "titel": "", "kapitel_ids": ["k3"]}])
    assert (v.anlegen, v.kapitel_id, v.kapitel_fehlt, v.titel) == (True, None, True, "Abschnitt 1")
    assert "Kapitel: Altes Kapitel" in v.beschreibung


def test_ersetztes_kapitel_nimmt_den_nachfolger():
    (v,) = _lauf([{"id": "a1", "titel": "", "kapitel_ids": ["k3"]}], nachfolger={"k3": "k2"})
    assert (v.anlegen, v.kapitel_id, v.kapitel_fehlt, v.titel) == (True, "k2", False, "Pythagoras")
    assert "Kapitel" not in v.beschreibung.split("\n", 1)[-1]
    # Hat die Gruppe am Nachfolger oder noch am alten Kapitel eine Einheit: überspringen
    assert _lauf([{"id": "a1", "kapitel_ids": ["k3"]}], nachfolger={"k3": "k2"}, kapitel_mit_einheit={"k2"})[0].grund == KAPITEL_VORHANDEN
    assert _lauf([{"id": "a1", "kapitel_ids": ["k3"]}], kapitel_mit_einheit={"k3"})[0].grund == KAPITEL_VORHANDEN


def test_zwei_abschnitte_ein_kapitel_je_eine_einheit():
    a, b = _lauf([{"id": "a1", "titel": "Teil 1", "sequenz_ids": ["s1"]},
                  {"id": "a2", "titel": "Teil 2", "sequenz_ids": ["s2"]}], planungsart="sequenz")
    assert (a.anlegen, b.anlegen, a.kapitel_id, b.kapitel_id) == (True, True, "k1", "k1")
    # Zweiter Lauf, nachdem Teil 1 angelegt wurde: Teil 2 entsteht trotzdem
    _, b = _lauf([{"id": "a1", "sequenz_ids": ["s1"]}, {"id": "a2", "sequenz_ids": ["s2"]}],
                 planungsart="sequenz", angelegte_abschnitte={"a1"})
    assert b.anlegen


def test_alle_termine_vorbei_und_ohne_termine():
    # Abschnitt Woche 3 (27.10.–31.10.): Termine Mo und Do; heute ist Freitag 31.10.
    v = _lauf([{"id": "x", "kapitel_ids": ["k1"]}, {"id": "y", "kapitel_ids": ["k2"]}], heute=date(2025, 10, 31))
    # Woche 1–2 (6.–17.10.) liegt ohnehin zurück
    assert v[0].grund == VORBEI
    lage = {**LAGE, "abschnitte": [{"von_woche": 3, "bis_woche": 3}]}
    (w,) = vorschau([{"id": "x", "kapitel_ids": ["k1"]}], lage, planungsart="kapitel", kapitel_von={}, titel=TITEL,
                    kapitel_aktiv={"k1"}, slots=_slots(), kapitel_mit_einheit=set(), angelegte_abschnitte=set(),
                    heute=date(2025, 10, 31))
    assert (w.anlegen, w.grund) == (False, VORBEI)
    # Ohne Termine in den Wochen (2. Halbjahr noch nicht erzeugt): Einheit ja, mit Hinweis
    (o,) = _lauf([{"id": "x", "kapitel_ids": ["k1"]}], slots=[])
    assert (o.anlegen, o.ohne_termine, o.stunden) == (True, True, 0)


def test_alles_schon_belegt():
    s = _slots()
    for x in s[:4]:
        x.ue_node_id = uuid4()
    (v,) = _lauf([{"id": "a1", "titel": "x", "kapitel_ids": ["k1"]}], slots=s)
    assert (v.anlegen, v.grund, v.belegt) == (False, BELEGT, 4)
