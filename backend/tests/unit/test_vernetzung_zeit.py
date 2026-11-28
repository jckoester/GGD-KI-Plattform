"""Zeit der Vernetzung (BE, Teil A, Schritt 2): Schuljahr je Stufe, Lage aus Plänen, Schätzung."""
import pytest

from app.context import vernetzung_zeit as vz
from app.context.absprachen_zeit import Spanne


def test_schuljahr_und_weg_einer_klasse():
    assert vz.schuljahre([7, 8, 9], "2026/27") == {7: "2026/27", 8: "2026/27", 9: "2026/27"}
    assert vz.schuljahre([8, 7], "2026/27", schuljahr="2027/28") == {7: "2027/28", 8: "2027/28"}
    # Die Klasse, die 2026/27 in Kl. 7 ist
    assert vz.schuljahre([5, 7, 8, 9], "2026/27", modus=vz.WEG, bezugsstufe=7) == {
        5: "2024/25", 7: "2026/27", 8: "2027/28", 9: "2028/29"}
    assert vz.verschoben("2099/00", 1) == "2100/01"
    with pytest.raises(ValueError):
        vz.schuljahre([7], "2026/27", modus=vz.WEG)


def test_plan_lagen_der_reihe_nach_mit_puffer_sequenzen_und_jahresende():
    abschnitte = [
        {"wochen": 3, "kapitel_ids": ["a"]},
        {"wochen": 2, "puffer": True},
        {"wochen": 4, "kapitel_ids": ["b"], "sequenz_ids": ["s1"]},
        {"wochen": 2, "kapitel_ids": ["a"]},          # a kommt wieder
        {"wochen": 5, "kapitel_ids": ["c"]},          # reicht über das Jahr hinaus
        {"wochen": 1, "kapitel_ids": ["d"]},          # ganz dahinter
    ]
    l = vz.plan_lagen(abschnitte, 8, vz.PLAN, kapitel_von_sequenz={"s1": "e"}, wochen_im_jahr=14)
    assert (l["a"].von_woche, l["a"].bis_woche) == (1, 11)
    assert (l["b"].von_woche, l["b"].bis_woche) == (6, 9) and (l["e"].von_woche, l["e"].bis_woche) == (6, 9)
    assert (l["c"].von_woche, l["c"].bis_woche) == (12, 14)
    assert "d" not in l and l["a"].stufe == 8 and l["a"].quelle == vz.PLAN


def test_schaetzen_mit_stunden_ueber_zwei_stufen():
    # 7/8-Curriculum, 2 Wochenstunden in 7, 3 in 8, je 10 Wochen
    l = vz.schaetzen([("a", 10), ("b", 14), ("c", 9)], [7, 8], {7: 2, 8: 3}, {7: 10, 8: 10})
    assert [(x.stufe, x.von_woche, x.bis_woche) for x in l["a"]] == [(7, 1, 5)]
    # b beginnt in Woche 6 von Kl. 7 (7 Wochen) und reicht in Kl. 8 hinein
    assert [(x.stufe, x.von_woche, x.bis_woche) for x in l["b"]] == [(7, 6, 10), (8, 1, 2)]
    assert [(x.stufe, x.von_woche, x.bis_woche) for x in l["c"]] == [(8, 3, 5)]
    assert all(x.quelle == vz.GESCHAETZT for xs in l.values() for x in xs)


def test_schaetzen_ohne_stunden_gleich_verteilt_und_abgeschnitten():
    l = vz.schaetzen([("a", None), ("b", 5), ("c", 5)], [9], {9: 3}, {9: 30})
    assert [(x.von_woche, x.bis_woche) for k in "abc" for x in l[k]] == [(1, 10), (11, 20), (21, 30)]
    # zu viele Stunden: was über das Jahr hinausreicht, fällt weg
    l = vz.schaetzen([("a", 60), ("b", 60), ("c", 60)], [9], {9: 2}, {9: 38})
    assert set(l) == {"a", "b"} and l["b"][0].bis_woche == 38
    assert vz.schaetzen([], [9], {}, {9: 38}) == {} and vz.schaetzen([("a", 1)], [9], {}, {}) == {}


def test_als_spanne_nutzt_schaetzung_nicht_fuer_wochen():
    plan = [vz.Lage(8, 3, 6, vz.PLAN), vz.Lage(8, 20, 22, vz.ENTWURF)]
    assert vz.als_spanne(plan) == Spanne(8, 8, 3, 22, entwurf=True)
    geschaetzt = [vz.Lage(7, 30, 38, vz.GESCHAETZT), vz.Lage(8, 1, 2, vz.GESCHAETZT)]
    assert vz.als_spanne(geschaetzt) == Spanne(7, 8)
    assert vz.als_spanne([], (9, None)) == Spanne(9, 9)
    assert vz.als_spanne([]) is None
