"""Unterrichtswochen als Takt der Budget-Zuteilung.

Die Eigenschaft, an der alles hängt: **Die Anzahl der Unterrichtswochen ist der Faktor der
Jahressumme.** Was die Administration je Jahrgang einträgt, wird mit dieser Zahl
multipliziert — stimmt sie nicht, weicht die Jahressumme von der Zusage ab, und zwar
unauffällig.
"""
from datetime import date

import pytest

from app.budget.schulwochen import (
    anzahl_unterrichtswochen,
    unterrichtswochen,
    woche_am,
    wochen_bis,
)
from app.planning.calendar import SchoolYearConfig


def _jahr(**over) -> SchoolYearConfig:
    """Ein kleines, vollständig überschaubares Schuljahr für die Kanten."""
    basis = dict(
        schuljahr="2026/27",
        beginn=date(2026, 9, 14),      # Montag
        ende=date(2026, 10, 16),       # Freitag
        halbjahreswechsel=date(2026, 10, 1),
        ferien=[],
        feiertage=[],
        unterrichtsfreie_tage=[],
    )
    basis.update(over)
    return SchoolYearConfig(**basis)


def test_fuenf_volle_wochen():
    cfg = _jahr()
    wochen = unterrichtswochen(cfg)

    assert [w.index for w in wochen] == [1, 2, 3, 4, 5]
    assert all(w.tage == 5 for w in wochen)
    assert anzahl_unterrichtswochen(cfg) == 5


def test_angebrochene_randwochen_zaehlen_voll():
    """Schuljahresbeginn am Mittwoch, Ende am Dienstag.

    Beide Randwochen sind unvollständig — und zählen trotzdem als je eine Zuteilung.
    Der Betrag hängt an der Woche, nicht an ihren Tagen; die Jahressumme bleibt damit
    genau ``Wochenbetrag × Wochenzahl``.
    """
    cfg = _jahr(beginn=date(2026, 9, 16), ende=date(2026, 10, 13))
    wochen = unterrichtswochen(cfg)

    assert wochen[0].tage == 3, "Mi–Fr"
    assert wochen[-1].tage == 2, "Mo–Di"
    assert anzahl_unterrichtswochen(cfg) == 5


def test_vergessener_feiertag_in_voller_woche_bleibt_folgenlos():
    """Die Robustheit, die das flache Modell gegenüber der Tagesrechnung gewinnt.

    Ein nicht eingetragener Feiertag mitten in der Woche verschiebt das Budget nicht —
    solange die Woche überhaupt noch Unterricht hat.
    """
    ohne = _jahr()
    mit = _jahr(feiertage=[{"name": "Fronleichnam", "datum": date(2026, 9, 23)}])

    assert anzahl_unterrichtswochen(mit) == anzahl_unterrichtswochen(ohne)


def test_ferienwochen_bekommen_keinen_index():
    """Der Grund, warum die Ferienfrage im Wochenmodell nicht gestellt werden muss."""
    cfg = _jahr(ferien=[{"name": "Herbst", "von": date(2026, 9, 21), "bis": date(2026, 9, 25)}])
    wochen = unterrichtswochen(cfg)

    assert date(2026, 9, 21) not in [w.montag for w in wochen]
    assert [w.index for w in wochen] == [1, 2, 3, 4], "durchgezählt, ohne Lücke"


def test_fehlender_ferienzeitraum_erhoeht_die_jahressumme():
    """Das verbleibende Restrisiko — als Test festgehalten, nicht nur als Kommentar.

    Eine ganze Woche, die die Seite wechselt, ist die einzige Art, wie eine schlampig
    gepflegte `school_year.yaml` die Budgetzusage überschreiten kann. Prüfpunkt beim
    Schuljahreswechsel.
    """
    gepflegt = _jahr(ferien=[{"name": "Herbst", "von": date(2026, 9, 21), "bis": date(2026, 9, 25)}])
    vergessen = _jahr()

    assert anzahl_unterrichtswochen(vergessen) == anzahl_unterrichtswochen(gepflegt) + 1


def test_woche_am_findet_auch_vom_wochenende_aus():
    """Ein Lauf am Samstag muss der Woche davor zugeordnet werden, nicht ins Leere."""
    cfg = _jahr()
    w = woche_am(date(2026, 9, 19), cfg)

    assert w is not None and w.index == 1


def test_woche_am_gibt_in_ferien_nichts_zurueck():
    cfg = _jahr(ferien=[{"name": "Herbst", "von": date(2026, 9, 21), "bis": date(2026, 9, 25)}])

    assert woche_am(date(2026, 9, 23), cfg) is None
    assert woche_am(date(2026, 8, 1), cfg) is None, "vor Schuljahresbeginn"


def test_wochen_bis_holt_ausgefallene_laeufe_nach():
    """Grundlage der Idempotenz: Was noch nicht gebucht ist, steht hier weiterhin drin."""
    cfg = _jahr()
    bis_dritte = wochen_bis(date(2026, 10, 1), cfg)  # Donnerstag der 3. Woche

    assert [w.index for w in bis_dritte] == [1, 2, 3]


def test_echtes_schuljahr_aus_der_beispielkonfiguration():
    """Regressionsanker gegen die Zahl, mit der die Bemessung gerechnet wurde."""
    import yaml
    from pathlib import Path

    pfad = Path(__file__).resolve().parents[3] / "config" / "school_year.example.yaml"
    cfg = SchoolYearConfig(**yaml.safe_load(pfad.read_text(encoding="utf-8")))

    assert anzahl_unterrichtswochen(cfg) == 40
    assert sum(w.tage for w in unterrichtswochen(cfg)) == 188, "Unterrichtstage 2026/27"
