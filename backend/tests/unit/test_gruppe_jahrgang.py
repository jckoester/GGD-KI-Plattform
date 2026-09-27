"""Die Jahrgangs-Ableitung aus dem Gruppennamen.

⚠️ Der Anlass: `curriculum_resolver` leitete den Jahrgang **ausschließlich** über
`group_source_classes` ab. Gruppen aus dem Stundenplan und Kursstufenkurse tragen dort
nichts — und ohne Jahrgang bot die Auflösung *alle* Curricula des Fachs an, einem
Abi-28-Kurs also „CH Kl. 8" (Befund 24.09.2026).
"""
import pytest

from app.groups.jahrgang import leite_jahrgang_ab

ENDE = 2027  # Schuljahr 2026/27


@pytest.mark.parametrize("name,erwartet", [
    ("nwt-tl-10abcd", 10),
    ("nwt-tl-9abcd", 9),
    ("10abcd nwt", 10),
    ("9abcd nwt", 9),
    ("9 Musik", 9),
    ("11 Geographie", 11),
    ("8D", 8),
])
def test_klassenzahl_im_namen(name, erwartet):
    """Die acht Gruppen des Dev-Bestands, an denen die Regel entstanden ist."""
    assert leite_jahrgang_ab(name, schuljahr_ende=ENDE) == erwartet


@pytest.mark.parametrize("name", ["ch-tl-abi28", "ch-ks-abi28", "CH Abi 28", "abi-2028"])
def test_abiturjahrgang_wird_zur_stufe(name):
    """Abitur 2028 heißt im Schuljahr 2026/27: Jahrgang 11."""
    assert leite_jahrgang_ab(name, schuljahr_ende=ENDE) == 11


def test_abitur_schlaegt_die_klassenregel():
    """⚠️ **Die Reihenfolge ist der Kern.**

    „ch-tl-abi28" enthält die Zahl 28. Prüfte die Klassenregel zuerst, käme ein 28.
    Jahrgang heraus — die Plausibilitätsschranke verwürfe ihn stillschweigend, und aus
    einer ableitbaren Gruppe würde eine ohne Jahrgang.
    """
    assert leite_jahrgang_ab("ch-tl-abi28", schuljahr_ende=ENDE) == 11
    assert leite_jahrgang_ab("ch-tl-abi28", schuljahr_ende=ENDE) != 28


def test_abiturjahrgang_wandert_mit_dem_schuljahr():
    # Dieselbe Kohorte, ein Jahr später: Kursstufe 2.
    assert leite_jahrgang_ab("abi28", schuljahr_ende=2028) == 12
    assert leite_jahrgang_ab("abi28", schuljahr_ende=2027) == 11


@pytest.mark.parametrize("name", [
    "Projektkurs", "Arbeitsgemeinschaft Schach", "", None,
    "nwt-tl-2024",   # eine Jahreszahl ist kein Jahrgang
    "abi99",         # längst vorbei → unplausibel
])
def test_erfindet_keinen_jahrgang(name):
    """Wo der Name nichts hergibt, bleibt es unbekannt — und ein Mensch entscheidet.

    Eine erfundene Stufe wäre schlimmer als keine: Sie sieht aus wie eine Entscheidung.
    """
    assert leite_jahrgang_ab(name, schuljahr_ende=ENDE) is None
