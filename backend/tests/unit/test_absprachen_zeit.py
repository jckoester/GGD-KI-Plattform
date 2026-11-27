"""Zeitprüfung der Absprachen (0.64, AY Teil 2, Schritt 7) — rein, ohne Datenbank."""
from datetime import date

import pytest

from app.context.absprachen_zeit import (
    DORT_OHNE_LAGE, EINGEHALTEN, HIER_OHNE_LAGE, OFFEN, OHNE_WOCHEN, VERLETZT, Spanne, beschreibung,
    kapitel_spannen, pruefe, vereinen,
)


def _l(von, bis, beginn=None, ende=None):
    return {"von_woche": von, "bis_woche": bis, "beginn": beginn or date(2026, 9, 14), "ende": ende}


def W(von, bis, stufe=8):
    return Spanne(stufe, stufe, von, bis)


def test_spannen_aus_dem_plan_mit_puffer_sequenzen_und_ausserhalb():
    abschnitte = [
        {"kapitel_ids": ["a"]},
        {"puffer": True, "kapitel_ids": []},
        {"kapitel_ids": ["b", "a"]},
        {"sequenz_ids": ["s1"]},
        {"kapitel_ids": ["c"]},
    ]
    lage = [_l(1, 3, date(2026, 9, 14), date(2026, 10, 2)), _l(4, 4), _l(5, 6, date(2026, 10, 19), date(2026, 10, 30)),
            _l(7, 8), {"von_woche": 40, "bis_woche": 41, "beginn": None, "ende": None}]
    s = kapitel_spannen(abschnitte, lage, 8, kapitel_von_sequenz={"s1": "d"})
    assert (s["a"].von_woche, s["a"].bis_woche, s["a"].beginn, s["a"].ende) == (1, 6, date(2026, 9, 14), date(2026, 10, 30))
    assert (s["b"].von_woche, s["b"].bis_woche) == (5, 6)
    assert (s["d"].von_woche, s["d"].bis_woche) == (7, 8)
    assert "c" not in s     # ganz hinter dem Schuljahr


@pytest.mark.parametrize("art,dort,erwartet", [
    ("vorher", W(1, 3), EINGEHALTEN),
    ("vorher", W(3, 5), EINGEHALTEN),     # endet in der Woche, in der hier beginnt
    ("vorher", W(4, 6), VERLETZT),
    ("vorher", W(10, 12), VERLETZT),
    ("nachher", W(10, 12), EINGEHALTEN),
    ("nachher", W(8, 9), EINGEHALTEN),    # beginnt in der letzten Woche von hier
    ("nachher", W(1, 3), VERLETZT),
    ("gleichzeitig", W(4, 6), EINGEHALTEN),
    ("gleichzeitig", W(8, 12), EINGEHALTEN),
    ("gleichzeitig", W(1, 4), VERLETZT),
    ("gleichzeitig", W(10, 12), VERLETZT),
])
def test_pruefe_mit_wochen(art, dort, erwartet):
    assert pruefe(art, W(5, 8), dort).ergebnis == erwartet


def test_verschiedene_stufen_entscheiden_auch_ohne_plan():
    hier = Spanne(8, 8)
    assert pruefe("vorher", hier, Spanne(7, 7)).ergebnis == EINGEHALTEN
    assert pruefe("vorher", hier, Spanne(9, 10)).ergebnis == VERLETZT
    assert pruefe("gleichzeitig", hier, Spanne(5, 6)).ergebnis == VERLETZT
    assert pruefe("nachher", W(30, 32, 8), W(1, 2, 9)).ergebnis == EINGEHALTEN   # Kl. 9 nach Kl. 8
    # Bänder, die sich überschneiden, ohne Wochen: offen
    assert pruefe("vorher", Spanne(7, 8), Spanne(8, 8)).grund == OHNE_WOCHEN
    # Nur eine Seite mit Wochen, gleiche Stufe: offen
    assert pruefe("vorher", W(5, 8), Spanne(8, 8)).ergebnis == OFFEN


def test_ohne_lage_und_abgestimmt():
    assert pruefe("abgestimmt", W(1, 2), W(3, 4)) is None
    assert pruefe("vorher", None, W(3, 4)).grund == HIER_OHNE_LAGE
    assert pruefe("vorher", W(3, 4), None).grund == DORT_OHNE_LAGE


def test_vereinen_ueber_zwei_stufen():
    s = vereinen([W(30, 34, 8), W(2, 4, 7)])
    assert (s.stufe_von, s.stufe_bis, s.von_woche, s.bis_woche) == (7, 8, 2, 34)
    s = vereinen([W(2, 4, 7), Spanne(8, 8)])
    assert (s.stufe_von, s.stufe_bis, s.mit_wochen) == (7, 8, False)
    assert vereinen([]) is None


def test_beschreibung():
    s = Spanne(8, 8, 1, 3, date(2026, 9, 14), date(2026, 10, 2))
    assert beschreibung(s) == "Kl. 8, KW 38–40"
    assert beschreibung(Spanne(8, 8, 1, 1, date(2026, 9, 14), None, True)) == "Kl. 8, KW 38 (Entwurf)"
    assert beschreibung(Spanne(7, 8)) == "Kl. 7/8"
    assert beschreibung(Spanne(5, 7)) == "Kl. 5–7"
    assert beschreibung(None) is None


def test_mit_echter_lage_ueber_die_herbstferien():
    """Die Wochen zählen Unterrichtswochen — Ferien dazwischen verschieben nichts."""
    from app.context.verlaufsplan import _lage_dict
    from app.planning.verlaufsplan_zeit import lage
    from tests.unit.test_verlaufsplan_zeit import KALENDER_2025_26

    m = [{"id": "1", "wochen": 6, "kapitel_ids": ["brueche"]}, {"id": "2", "wochen": 4, "kapitel_ids": ["x"]}]
    ph = [{"id": "1", "wochen": 7, "kapitel_ids": ["y"]}, {"id": "2", "wochen": 3, "kapitel_ids": ["dichte"]}]
    sm = kapitel_spannen(m, _lage_dict(lage(m, KALENDER_2025_26))["abschnitte"], 8)
    sp = kapitel_spannen(ph, _lage_dict(lage(ph, KALENDER_2025_26))["abschnitte"], 8)
    assert (sm["brueche"].von_woche, sm["brueche"].bis_woche) == (1, 6)
    assert (sp["dichte"].von_woche, sp["dichte"].bis_woche) == (8, 10)
    # Physik hält „Brüche vorher“ ein, „gleichzeitig“ nicht
    assert pruefe("vorher", sp["dichte"], sm["brueche"]).ergebnis == EINGEHALTEN
    assert pruefe("gleichzeitig", sp["dichte"], sm["brueche"]).ergebnis == VERLETZT
    assert sp["dichte"].beginn > sm["brueche"].ende
