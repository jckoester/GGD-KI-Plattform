"""Hochrechnung des Schuljahresverbrauchs.

Ihr Zweck ist der Zeitpunkt: Im Juli weiß jeder, ob die Schule unter ihrer Zusage geblieben
ist — dann nützt es niemandem. Im März kann sie die Wochenbeträge fürs zweite Halbjahr
anheben, statt am Jahresende einen Rest zu verwalten.
"""
import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.budget.forecast import BELASTBAR_AB_WOCHEN, hochrechnen


def test_lineare_fortschreibung():
    """Zehn Wochen à 10 € auf 40 Wochen: 400 €."""
    h = hochrechnen(verbraucht_eur=100.0, wochen_vergangen=10, wochen_gesamt=40)

    assert h.erwartet_eur == 400.0
    assert h.verbraucht_eur == 100.0


def test_auslastung_gegen_die_zusage():
    h = hochrechnen(
        verbraucht_eur=100.0, wochen_vergangen=10, wochen_gesamt=40, zugeteilt_eur=2000.0
    )

    assert h.erwartet_eur == 400.0
    assert h.auslastung == pytest.approx(0.2), "ein Fünftel der Zusage"


def test_ohne_vergangene_woche_keine_hochrechnung():
    """Vor Schuljahresbeginn gibt es nichts fortzuschreiben — und keine Division durch 0."""
    h = hochrechnen(verbraucht_eur=0.0, wochen_vergangen=0, wochen_gesamt=40)

    assert h.erwartet_eur is None
    assert h.auslastung is None


def test_ohne_zusage_keine_auslastung():
    """Sind keine Nutzer erfasst, ist der Anteil an einer Zusage von 0 keine Aussage."""
    h = hochrechnen(verbraucht_eur=50.0, wochen_vergangen=5, wochen_gesamt=40)

    assert h.erwartet_eur == 400.0
    assert h.auslastung is None


@pytest.mark.parametrize(
    "wochen, erwartet_belastbar",
    [(1, False), (BELASTBAR_AB_WOCHEN - 1, False), (BELASTBAR_AB_WOCHEN, True), (20, True)],
)
def test_belastbarkeit_haengt_an_der_zahl_der_wochen(wochen, erwartet_belastbar):
    """Die Zahl wird früh gezeigt, aber als unsicher gekennzeichnet.

    In Woche 2 verdoppelt eine einzelne Projektwoche die Hochrechnung. Sie zu verschweigen
    hieße aber, die Administration bis Weihnachten im Dunkeln zu lassen — also lieber
    zeigen und dazuschreiben, worauf sie beruht.
    """
    h = hochrechnen(verbraucht_eur=10.0, wochen_vergangen=wochen, wochen_gesamt=40)

    assert h.belastbar is erwartet_belastbar
    assert h.erwartet_eur is not None, "auch früh wird gerechnet"


def test_ueberschreitung_wird_nicht_gedeckelt():
    """Läuft die Schule über ihre Zusage, muss die Zahl das zeigen — nicht bei 100 % enden."""
    h = hochrechnen(
        verbraucht_eur=600.0, wochen_vergangen=10, wochen_gesamt=40, zugeteilt_eur=2000.0
    )

    assert h.erwartet_eur == 2400.0
    assert h.auslastung == pytest.approx(1.2)
