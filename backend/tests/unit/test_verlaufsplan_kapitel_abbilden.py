"""Kapitel eines alten Verlaufsplans auf die Curricula von heute legen (BD Schritt 6)."""
from app.context.verlaufsplan import kapitel_abbilden

CURRICULA = [{"kapitel": [{"id": "k1", "titel": "Ähnlichkeit"}, {"id": "k2", "titel": "Pythagoras"}]},
             {"kapitel": [{"id": "k3", "titel": "Pythagoras"}, {"id": "k4", "titel": "Kreise"}]}]


def test_bleibt_wird_per_titel_gefunden_oder_entfaellt():
    aus, entfallen = kapitel_abbilden(
        [{"titel": "A", "kapitel_ids": ["k1", "alt-kreise", "alt-pyth", "weg"]}],
        CURRICULA, {"alt-kreise": " kreise ", "alt-pyth": "Pythagoras"})
    # k1 bleibt; Kreise eindeutig → k4; Pythagoras zweimal vorhanden → nicht geraten; weg ohne Titel
    assert aus[0]["kapitel_ids"] == ["k1", "k4"]
    assert entfallen == 2
    assert aus[0]["titel"] == "A"


def test_doppelte_treffer_einmal():
    aus, entfallen = kapitel_abbilden([{"kapitel_ids": ["k1", "alt"]}], CURRICULA, {"alt": "Ähnlichkeit"})
    assert aus[0]["kapitel_ids"] == ["k1"] and entfallen == 0


def test_ohne_kapitel():
    assert kapitel_abbilden([{"wochen": 2}], CURRICULA) == ([{"wochen": 2, "kapitel_ids": []}], 0)
