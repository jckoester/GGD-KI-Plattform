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


# ── Sequenzen (Schritt 7) ─────────────────────────────────────────────────────
from app.context.verlaufsplan import SEQUENZ, bezuege_abbilden  # noqa: E402

MIT_SEQUENZEN = [{"kapitel": [
    {"id": "k1", "titel": "Ähnlichkeit", "sequenzen": [{"id": "s1", "titel": "Einführung"}, {"id": "s2", "titel": "Strahlensätze"}]},
    {"id": "k2", "titel": "Pythagoras", "sequenzen": [{"id": "s3", "titel": "Einführung"}, {"id": "s4", "titel": "Anwendungen"}]},
]}]


def test_sequenz_bleibt_oder_wird_unter_gleichem_kapitel_gefunden():
    aus, entfallen = bezuege_abbilden(
        [{"sequenz_ids": ["s4", "alt-einf", "alt-strahl", "alt-einf-fremd", "weg"], "kapitel_ids": ["k9"]}],
        MIT_SEQUENZEN, SEQUENZ,
        titel_alt={"alt-einf": "Einführung", "alt-strahl": "Strahlensätze", "alt-einf-fremd": "Einführung"},
        kapitel_alt={"alt-einf": "Pythagoras", "alt-strahl": "Ganz anderes Kapitel", "alt-einf-fremd": "Kreise"})
    # s4 bleibt; „Einführung“ unter Pythagoras → s3; Strahlensätze global eindeutig → s2;
    # „Einführung“ unter einem Kapitel, das es nicht mehr gibt, ist zweideutig → entfällt; weg entfällt
    assert aus[0]["sequenz_ids"] == ["s4", "s3", "s2"]
    assert entfallen == 2
    # Das Kapitelfeld bleibt unberührt — es gilt bei sequenzgenauer Planung nicht
    assert aus[0]["kapitel_ids"] == ["k9"]
