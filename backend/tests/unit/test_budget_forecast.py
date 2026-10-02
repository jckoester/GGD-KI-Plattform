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


# ── Verlauf: Ist gegen Soll (0.12, Paket 2, AP2) ─────────────────────────────

from datetime import date as _date

from app.budget.forecast import verlauf

# Schuljahr über fünf Kalenderwochen, die dritte sind Ferien.
_MO = [_date(2026, 9, 14), _date(2026, 9, 21), _date(2026, 9, 28),
       _date(2026, 10, 5), _date(2026, 10, 12)]
_UNTERRICHT = {_MO[0], _MO[1], _MO[3], _MO[4]}


def _verlauf(heute=_date(2026, 10, 16), ist=None):
    return verlauf(
        beginn=_MO[0], ende=_date(2026, 10, 16), unterrichts_montage=_UNTERRICHT,
        wochensumme_eur=10.0, ist_je_woche=ist or {}, heute=heute,
    )


def test_soll_ist_eine_treppe_in_den_ferien_flach():
    """⚠️ Eine Gerade läge in den Ferien über der Wirklichkeit und würde die Schule
    fälschlich beruhigen. Die Ferienwoche bleibt flach."""
    assert [p.soll_eur for p in _verlauf()] == [10.0, 20.0, 20.0, 30.0, 40.0]


def test_ferienwoche_ist_als_solche_markiert():
    assert [p.unterricht for p in _verlauf()] == [True, True, False, True, True]


def test_ist_ist_kumuliert_und_laeuft_auch_in_den_ferien():
    """Wer Guthaben angesammelt hat, darf es in den Ferien nutzen — gezählt wird, was
    tatsächlich verbraucht wurde."""
    ist = {_MO[0]: 1.0, _MO[2]: 0.5, _MO[3]: 2.0}
    assert [p.ist_eur for p in _verlauf(ist=ist)] == [1.0, 1.0, 1.5, 3.5, 3.5]


def test_zukunft_hat_kein_ist():
    """Eine Null für kommende Wochen sähe aus wie „nichts verbraucht"."""
    punkte = _verlauf(heute=_date(2026, 9, 23), ist={_MO[0]: 1.0, _MO[1]: 1.0})
    assert [p.ist_eur for p in punkte] == [1.0, 2.0, None, None, None]
    # Die Zusage dagegen steht für das ganze Jahr fest.
    assert punkte[-1].soll_eur == 40.0


def test_endpunkt_ist_die_jahreszusage():
    """Letzter Soll-Wert = Wochensumme × Unterrichtswochen — dieselbe Zahl, die die
    Hochrechnung als „zugeteilt" führt."""
    assert _verlauf()[-1].soll_eur == 10.0 * len(_UNTERRICHT)


def test_beginn_mitten_in_der_woche():
    """Das Schuljahr beginnt nicht immer montags — die Woche zählt trotzdem ab ihrem
    Montag, wie bei der Zuteilung."""
    punkte = verlauf(
        beginn=_date(2026, 9, 16), ende=_date(2026, 9, 25),
        unterrichts_montage={_MO[0], _MO[1]}, wochensumme_eur=1.0,
        ist_je_woche={}, heute=_date(2026, 9, 25),
    )
    assert [p.montag for p in punkte] == [_MO[0], _MO[1]]
