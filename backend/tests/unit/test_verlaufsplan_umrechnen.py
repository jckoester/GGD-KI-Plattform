"""Planungsart wechseln (BD Schritt 7): Sequenzen ↔ Kapitel."""
from app.context.verlaufsplan import KAPITEL, SEQUENZ, planungsart, umrechnen

KAPITEL_VON = {"s1": "k1", "s2": "k1", "s3": "k2"}
SEQUENZEN_VON = {"k1": ["s1", "s2"], "k2": ["s3"]}


def test_nach_kapitel_ohne_doppel_und_unbekannte_weg():
    aus = umrechnen([{"titel": "A", "sequenz_ids": ["s2", "s1", "s3", "fremd"]}], KAPITEL,
                    kapitel_von=KAPITEL_VON, sequenzen_von=SEQUENZEN_VON)
    assert aus == [{"titel": "A", "sequenz_ids": ["s2", "s1", "s3", "fremd"], "kapitel_ids": ["k1", "k2"]}]


def test_nach_sequenz_alle_des_kapitels():
    aus = umrechnen([{"kapitel_ids": ["k2", "k1", "k1"]}, {"kapitel_ids": []}], SEQUENZ,
                    kapitel_von=KAPITEL_VON, sequenzen_von=SEQUENZEN_VON)
    assert [a["sequenz_ids"] for a in aus] == [["s3", "s1", "s2"], []]


def test_planungsart_vorgabe_fuer_altbestand():
    assert planungsart({}) == KAPITEL
    assert planungsart({"planungsart": "sequenz"}) == SEQUENZ
    assert planungsart({"planungsart": "quatsch"}) == KAPITEL
