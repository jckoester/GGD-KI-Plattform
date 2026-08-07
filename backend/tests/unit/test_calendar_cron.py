"""UP-8 Schritt 10a — täglicher Abgleich als Cron.

Die Abnahme aus dem Plan steht im Mittelpunkt: Ein Lauf gegen eine nicht erreichbare
Quelle darf **nichts** ändern. Die Jahresplanung ist Handarbeit; sie zu verwerfen, weil ein
fremder Server kurz nicht antwortet, wäre der teuerste denkbare Fehler.
"""
from datetime import date

import pytest

from app.calendar.base import AuthenticationError, CalendarSourceError
from app.crons.calendar_sync_service import (
    SyncStats,
    _status_fuer,
    run_calendar_sync,
)


class FakeDB:
    """Merkt sich, was geschrieben wurde — mehr braucht der Lauf nicht."""

    def __init__(self, pseudonyme=("p1", "p2")):
        self.pseudonyme = list(pseudonyme)
        self.status_writes: list[dict] = []
        self.andere_writes: list[str] = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "FROM user_preferences" in sql:
            class R:
                def __init__(self, rows):
                    self._rows = rows

                def fetchall(self):
                    return self._rows

            return R([(p,) for p in self.pseudonyme])
        if "calendar_sync_status" in sql:
            self.status_writes.append(params or {})
        else:
            self.andere_writes.append(sql)

        class Leer:
            def fetchall(self_):
                return []

            def fetchone(self_):
                return None

        return Leer()

    async def commit(self):
        self.commits += 1


@pytest.fixture
def eingerichtet(monkeypatch):
    monkeypatch.setattr("app.crons.calendar_sync_service.is_configured", lambda: True)


# ── Abnahme: nicht erreichbare Quelle ────────────────────────────────────────


@pytest.mark.asyncio
async def test_nicht_erreichbare_quelle_aendert_nichts(eingerichtet, monkeypatch):
    """Abnahme aus dem Plan.

    Keine Datenänderung, Status gesetzt, Slots unberührt — `apply_sync` wird gar nicht
    erst erreicht.
    """
    async def kaputt(*args, **kwargs):
        raise CalendarSourceError("WebUntis nicht erreichbar (ConnectError)")

    monkeypatch.setattr("app.calendar.router._stundenplan_abgleich", kaputt)
    angewendet = []
    monkeypatch.setattr(
        "app.crons.calendar_sync_service.apply_sync",
        lambda *a, **k: angewendet.append(a),
    )

    db = FakeDB()
    stats = await run_calendar_sync(db)

    assert stats.fehlgeschlagen == 2 and stats.geaendert == 0
    assert angewendet == []                     # nichts geschrieben
    assert db.andere_writes == []               # kein UPDATE auf lesson_slots
    assert {w["s"] for w in db.status_writes} == {"nicht_erreichbar"}


@pytest.mark.asyncio
async def test_eine_fehlerhafte_lehrkraft_stoppt_den_lauf_nicht(eingerichtet, monkeypatch):
    """Ein Kürzel, das WebUntis nicht kennt, darf nicht die übrigen 89 blockieren."""
    from app.calendar.sync import SyncPlan

    async def teils(db, pseudonym, wochen, bis):
        if pseudonym == "p1":
            raise CalendarSourceError("WebUntis kennt das Kürzel 'XXX' nicht.")
        return SyncPlan(), {"kuerzel": "OK"}, None

    monkeypatch.setattr("app.calendar.router._stundenplan_abgleich", teils)

    async def apply(db, plan):
        return 3

    monkeypatch.setattr("app.crons.calendar_sync_service.apply_sync", apply)

    stats = await run_calendar_sync(FakeDB(("p1", "p2")))
    assert stats.fehlgeschlagen == 1
    assert stats.erfolgreich == 1
    assert stats.geaendert == 3


@pytest.mark.asyncio
async def test_ohne_quelle_passiert_nichts(monkeypatch):
    monkeypatch.setattr("app.crons.calendar_sync_service.is_configured", lambda: False)
    db = FakeDB()
    stats = await run_calendar_sync(db)
    assert stats == SyncStats()
    assert db.status_writes == []


@pytest.mark.asyncio
async def test_dry_run_schreibt_nicht(eingerichtet, monkeypatch):
    from app.calendar.sync import SyncPlan

    async def ok(db, pseudonym, wochen, bis):
        return SyncPlan(), {"kuerzel": "OK"}, None

    monkeypatch.setattr("app.calendar.router._stundenplan_abgleich", ok)
    angewendet = []
    monkeypatch.setattr(
        "app.crons.calendar_sync_service.apply_sync",
        lambda *a, **k: angewendet.append(a),
    )
    db = FakeDB(("p1",))
    stats = await run_calendar_sync(db, dry_run=True)
    assert angewendet == [] and db.status_writes == []
    assert stats.erfolgreich == 1


@pytest.mark.asyncio
async def test_fehlendes_kuerzel_bekommt_eigenen_status(eingerichtet, monkeypatch):
    async def ohne(db, pseudonym, wochen, bis):
        return None, None, "Im Profil ist kein Kürzel eingetragen."

    monkeypatch.setattr("app.calendar.router._stundenplan_abgleich", ohne)
    db = FakeDB(("p1",))
    await run_calendar_sync(db)
    assert db.status_writes[0]["s"] == "kein_kuerzel"


@pytest.mark.asyncio
async def test_erfolg_wird_mit_zahlen_festgehalten(eingerichtet, monkeypatch):
    """Damit die Anzeige in 10b sagen kann, was passiert ist — nicht nur, dass etwas war."""
    from app.calendar.sync import ShiftSuggestion, SyncConflict, SyncPlan

    plan = SyncPlan(
        conflicts=[SyncConflict(date(2026, 6, 8), 3, "pinned", "x")],
        verlegungen=[
            ShiftSuggestion(1, None, date(2026, 6, 8), 3, date(2026, 6, 9), 4)
        ],
    )

    async def ok(db, pseudonym, wochen, bis):
        return plan, {"kuerzel": "AK"}, None

    monkeypatch.setattr("app.calendar.router._stundenplan_abgleich", ok)

    async def apply(db, p):
        return 7

    monkeypatch.setattr("app.crons.calendar_sync_service.apply_sync", apply)

    db = FakeDB(("p1",))
    await run_calendar_sync(db)
    eintrag = db.status_writes[0]
    assert (eintrag["s"], eintrag["c"], eintrag["k"], eintrag["v"]) == ("ok", 7, 1, 1)


# ── Fehlerübersetzung ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "exc,status",
    [
        (AuthenticationError("Anmeldung fehlgeschlagen"), "anmeldung_fehlgeschlagen"),
        (CalendarSourceError("WebUntis nicht erreichbar (ReadTimeout)"), "nicht_erreichbar"),
        (CalendarSourceError("WebUntis antwortete mit HTTP 503"), "nicht_erreichbar"),
        (CalendarSourceError("Kürzel unbekannt"), "fehler"),
        (RuntimeError("irgendwas"), "fehler"),
    ],
)
def test_status_unterscheidet_die_ursachen(exc, status):
    """Ein Sammelstatus ließe die Lehrkraft raten, ob ihr Kürzel falsch ist oder der
    Server streikt — zwei Ursachen mit sehr verschiedenen Konsequenzen."""
    assert _status_fuer(exc)[0] == status


def test_unerwarteter_fehler_verraet_keine_interna():
    """Der Statustext wird angezeigt — eine durchgereichte Ausnahme könnte Pfade oder
    Zugangsdaten enthalten."""
    meldung = _status_fuer(RuntimeError("connect to postgres://user:pw@host failed"))[1]
    assert "pw@host" not in meldung
    assert meldung == "RuntimeError"


# ── Abgleichfenster (Handabgleich, 07.08.2026) ───────────────────────────────


def _cfg_mit_pfingstferien():
    from app.planning.calendar import SchoolYearConfig

    return SchoolYearConfig(
        schuljahr="2025/26",
        beginn=date(2025, 9, 15),
        ende=date(2026, 7, 29),
        halbjahreswechsel=date(2026, 2, 2),
        ferien=[{"name": "Pfingstferien", "von": date(2026, 5, 25), "bis": date(2026, 6, 5)}],
        feiertage=[],
        unterrichtsfreie_tage=[],
    )


@pytest.fixture
def kalender(monkeypatch):
    from app.calendar import router as kalender_router
    from app.planning import calendar as planungskalender

    monkeypatch.setattr(planungskalender, "load_school_year", _cfg_mit_pfingstferien)
    monkeypatch.setattr(kalender_router, "load_school_year", _cfg_mit_pfingstferien)
    return kalender_router


def test_abgleich_enthaelt_die_laufende_woche(kalender):
    """Der Kern des Problems: Änderungen betreffen **heute**.

    Das Musterfenster sucht den jüngsten zusammenhängenden Lauf und landet nach Ferien
    wochenlang in der Vergangenheit — für den Abgleich wäre das genau verkehrt.
    """
    mittwoch = date(2026, 6, 10)
    muster = kalender._unterrichtswochen(mittwoch, 4)
    abgleich = kalender._abgleich_wochen(mittwoch, 4)

    assert date(2026, 6, 8) not in muster        # Musterfenster: hinter den Ferien
    assert date(2026, 6, 8) in abgleich          # Abgleichfenster: die laufende Woche


def test_abgleich_schaut_nach_vorn(kalender):
    """Eine Verlegung zeigt fast immer in die Zukunft — ein reiner Rückblick fände den
    Ursprung und nie das Ziel."""
    abgleich = kalender._abgleich_wochen(date(2026, 6, 10), 1, vorausschau=2)
    assert abgleich == [date(2026, 6, 8), date(2026, 6, 15), date(2026, 6, 22)]


def test_abgleich_ueberspringt_ferienwochen(kalender):
    """Lücken sind hier erlaubt — anders als beim Muster, das Zusammenhang braucht."""
    abgleich = kalender._abgleich_wochen(date(2026, 6, 1), rueckblick=3, vorausschau=1)
    assert date(2026, 5, 25) not in abgleich     # Pfingstferien
    assert date(2026, 6, 8) in abgleich


def test_abgleich_bleibt_im_schuljahr(kalender):
    abgleich = kalender._abgleich_wochen(date(2026, 7, 27), 1, vorausschau=4)
    assert all(w <= date(2026, 7, 29) for w in abgleich)
