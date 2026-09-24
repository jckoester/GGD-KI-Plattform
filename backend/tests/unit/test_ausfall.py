"""Die reine Regel für den persönlichen Ausfall (Paket 5, AP4)."""
from dataclasses import dataclass
from datetime import date
from typing import Optional
from uuid import UUID, uuid4

import pytest

from app.planning.ausfall import plane_ausfall, plane_ruecknahme

HEUTE = date(2026, 11, 10)
MORGEN = date(2026, 11, 11)


@dataclass
class Slot:
    id: UUID
    group_id: int
    date: date
    kategorie: str = "unterricht"
    ausfall_herkunft: Optional[str] = None
    ausfall_vorher: Optional[str] = None


def _s(gid=1, tag=HEUTE, **kw):
    return Slot(id=uuid4(), group_id=gid, date=tag, **kw)


# ── Markieren ────────────────────────────────────────────────────────────────


def test_ganzer_tag_trifft_alle_gruppen():
    """Fortbildung und Krankheit gelten nicht je Fach."""
    slots = [_s(gid=1), _s(gid=2), _s(gid=3, tag=MORGEN)]
    treffer = plane_ausfall(slots, datum=HEUTE, reichweite="tag")
    assert {m.group_id for m in treffer} == {1, 2}


def test_eine_gruppe_laesst_die_anderen_in_ruhe():
    slots = [_s(gid=1), _s(gid=2)]
    treffer = plane_ausfall(slots, datum=HEUTE, reichweite="gruppe", group_id=1)
    assert [m.group_id for m in treffer] == [1]


def test_merkt_sich_was_ueberschrieben_wird():
    """⚠️ **Nicht `unterricht` annehmen.**

    Krankheit am Klausurtag ist genau der Fall, in dem der Rückweg sonst die Prüfung
    verlöre — aus einer Klassenarbeit würde eine gewöhnliche Stunde.
    """
    treffer = plane_ausfall([_s(kategorie="pruefung")], datum=HEUTE, reichweite="tag")
    assert [m.vorher for m in treffer] == ["pruefung"]


def test_schon_ausgefallene_stunden_bleiben_unangetastet():
    """⚠️ Ein zweites Markieren überschriebe `ausfall_vorher` mit `'ausfall'` — der
    Rückweg führte dann nirgendwohin."""
    slots = [_s(kategorie="ausfall", ausfall_herkunft="stundenplan",
                ausfall_vorher="unterricht")]
    assert plane_ausfall(slots, datum=HEUTE, reichweite="tag") == ()


def test_ein_anderer_tag_ist_nicht_betroffen():
    assert plane_ausfall([_s(tag=MORGEN)], datum=HEUTE, reichweite="tag") == ()


def test_reichweite_gruppe_ohne_gruppe_ist_ein_fehler():
    """Sonst träfe ein Tippfehler im Aufruf still den ganzen Tag."""
    with pytest.raises(ValueError):
        plane_ausfall([_s()], datum=HEUTE, reichweite="gruppe")


def test_unbekannte_reichweite_wird_abgewiesen():
    with pytest.raises(ValueError):
        plane_ausfall([_s()], datum=HEUTE, reichweite="halbtags")


# ── Zurücknehmen ─────────────────────────────────────────────────────────────


def test_ruecknahme_stellt_den_vorzustand_her():
    slots = [_s(kategorie="ausfall", ausfall_herkunft="eigen", ausfall_vorher="pruefung")]
    assert [r.zurueck_auf for r in plane_ruecknahme(
        slots, datum=HEUTE, reichweite="tag")] == ["pruefung"]


def test_ruecknahme_laesst_den_stundenplan_in_ruhe():
    """⚠️ Ein Ausfall aus dem Stundenplan gehört dem Abgleich.

    Ihn hier zu entfernen hieße, eine Auskunft der Schule zu überschreiben — die beim
    nächsten Lauf ohnehin wiederkäme.
    """
    slots = [_s(kategorie="ausfall", ausfall_herkunft="stundenplan")]
    assert plane_ruecknahme(slots, datum=HEUTE, reichweite="tag") == ()


def test_ruecknahme_nimmt_auch_einzeln_gesetztes_mit():
    """Entschieden am 24.09.2026 (F4): hinnehmbar — aber die Oberfläche sagt es vorher.

    Nach dem Schreiben ist nicht mehr unterscheidbar, ob ein Slot über „ganzer Tag" oder
    einzeln markiert wurde; beide tragen `herkunft = 'eigen'`.
    """
    slots = [_s(gid=1, kategorie="ausfall", ausfall_herkunft="eigen"),
             _s(gid=2, kategorie="ausfall", ausfall_herkunft="eigen")]
    assert len(plane_ruecknahme(slots, datum=HEUTE, reichweite="tag")) == 2


def test_ohne_gemerkten_vorzustand_geht_es_auf_unterricht():
    """Der Bestand aus Migration 0075 kennt keinen Vorzustand."""
    slots = [_s(kategorie="ausfall", ausfall_herkunft="eigen", ausfall_vorher=None)]
    assert [r.zurueck_auf for r in plane_ruecknahme(
        slots, datum=HEUTE, reichweite="tag")] == ["unterricht"]


def test_ruecknahme_beruehrt_keine_laufende_stunde():
    slots = [_s(kategorie="unterricht")]
    assert plane_ruecknahme(slots, datum=HEUTE, reichweite="tag") == ()


# ── setze_kategorie: die drei Felder bewegen sich zusammen ───────────────────


def test_setze_kategorie_merkt_sich_den_vorzustand():
    from app.planning.ausfall import setze_kategorie

    s = _s(kategorie="pruefung")
    setze_kategorie(s, "ausfall", herkunft="eigen")
    assert (s.kategorie, s.ausfall_herkunft, s.ausfall_vorher) == (
        "ausfall", "eigen", "pruefung")


def test_setze_kategorie_raeumt_beim_verlassen_auf():
    """⚠️ Eine zurückgebliebene Herkunft an einer Stunde, die wieder stattfindet, führte
    beim nächsten Zurücknehmen auf eine Kategorie, die niemand gesetzt hat."""
    from app.planning.ausfall import setze_kategorie

    s = _s(kategorie="ausfall", ausfall_herkunft="eigen", ausfall_vorher="pruefung")
    setze_kategorie(s, "unterricht", herkunft="eigen")
    assert (s.ausfall_herkunft, s.ausfall_vorher) == (None, None)


def test_setze_kategorie_ueberschreibt_den_vorzustand_nicht():
    """Zweimal Ausfall hintereinander darf `ausfall_vorher` nicht auf `'ausfall'` setzen —
    der Rückweg führte sonst nirgendwohin."""
    from app.planning.ausfall import setze_kategorie

    s = _s(kategorie="ausfall", ausfall_herkunft="stundenplan", ausfall_vorher="pruefung")
    setze_kategorie(s, "ausfall", herkunft="eigen")
    assert s.ausfall_vorher == "pruefung"
    assert s.ausfall_herkunft == "eigen"


def test_setze_kategorie_weist_unbekannte_herkunft_ab():
    from app.planning.ausfall import setze_kategorie

    with pytest.raises(ValueError):
        setze_kategorie(_s(), "ausfall", herkunft="irgendwoher")
