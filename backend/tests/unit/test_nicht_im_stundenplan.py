"""AP5: Der Hinweis „im Stundenplan nicht gefunden" — und sein Lärmfilter.

Die Meldung ist nur so viel wert wie ihre Auswahl. Eine Lehrkraft hat Gruppen aus dem
anderen Halbjahr und aus Vorjahren; würden die mitgemeldet, ginge der eine echte Fall
in einer Liste unter, die man nach zwei Wochen wegklickt.
"""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.groups.aktualitaet import ist_aktuell

SCHULJAHR = SimpleNamespace(
    beginn=date(2026, 9, 14),
    ende=date(2027, 7, 28),
    schuljahr="2026/27",
)
FRUEHER = datetime(2025, 9, 15, tzinfo=timezone.utc)
HEUTE = datetime(2026, 9, 20, tzinfo=timezone.utc)


def _gruppe(**kwargs):
    vorgabe = dict(id=1, type="teaching_group", sso_group_id=None, created_at=HEUTE)
    vorgabe.update(kwargs)
    return SimpleNamespace(**vorgabe)


def test_gruppe_mit_stunden_im_laufenden_jahr_gilt_als_aktuell():
    assert ist_aktuell(_gruppe(created_at=FRUEHER), {1}, SCHULJAHR)


def test_gruppe_aus_dem_vorjahr_ohne_beleg_gilt_nicht_als_aktuell():
    """⚠️ **Der Lärmfilter.** Ohne ihn meldete der Hinweis jedes Vorjahr.

    Eine Lehrkraft sammelt über Jahre Gruppen an. Eine Meldung, die sie alle nennt,
    sagt nichts über den einen Kurs, der gerade ausgelaufen ist.
    """
    assert not ist_aktuell(_gruppe(created_at=FRUEHER), set(), SCHULJAHR)


def test_frisch_angelegte_gruppe_gilt_als_aktuell():
    """Sie hat noch nichts, woran man sie erkennen könnte — und ist trotzdem neu."""
    assert ist_aktuell(_gruppe(created_at=HEUTE), set(), SCHULJAHR)


def test_gruppe_aus_dem_schulkonto_gilt_immer_als_aktuell():
    """Steht sie im Token, gibt es sie — der Immediate Mirror räumt den Rest ab."""
    assert ist_aktuell(
        _gruppe(sso_group_id="unterricht.9a.m", created_at=FRUEHER), set(), SCHULJAHR
    )


@pytest.mark.parametrize("typ", ["school_class", "subject_department", "activity_group"])
def test_nur_unterrichtsgruppen_werden_beurteilt(typ):
    """Klassen und Fachschaften kennen kein Schuljahresende in diesem Sinne."""
    assert ist_aktuell(_gruppe(type=typ, created_at=FRUEHER), set(), SCHULJAHR)
