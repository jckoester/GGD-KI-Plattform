"""Der Löschlauf für Rückmeldungen (ADR-020, ADR-011 §6.2).

Gegen die Datenbank, nicht gegen Mocks: Die Zusage steckt in der Frist — welche Zeile
das `WHERE` trifft und welche einen Tag zu jung ist.
"""
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.crons.feedback_cleanup_service import (
    AUFBEWAHRUNG_TAGE,
    HINWEIS_AB_TAGEN,
    cleanup_feedback,
)
from tests.integration.conftest import STUDENT_PSEUDO

MELDUNG = "Der Knopf zum Abschicken reagiert auf dem Handy nicht."


@pytest.fixture(scope="module")
def sync_conn(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def leere_tabelle(sync_conn):
    def raeumen():
        sync_conn.rollback()
        with sync_conn.cursor() as cur:
            cur.execute("DELETE FROM feedback WHERE pseudonym = %s", (STUDENT_PSEUDO,))
        sync_conn.commit()

    raeumen()
    yield
    raeumen()


# Stichtag im Jahr 2000: Der Lauf fasst **jede** fällige Zeile an, auch fremde
# Testdaten in derselben Datenbank. Nur die hier angelegten liegen davor.
JETZT = datetime(2000, 6, 1, tzinfo=timezone.utc)


def _meldung(sync_conn, *, status, gewechselt_vor=None, erstellt_vor=timedelta(0)):
    fid = uuid.uuid4()
    erstellt = JETZT - erstellt_vor
    gewechselt = None if gewechselt_vor is None else JETZT - gewechselt_vor
    sync_conn.rollback()
    with sync_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO feedback (id, pseudonym, role, category, content, app_version,"
            " status, created_at, status_changed_at) VALUES"
            " (%s,%s,'student','bug',%s,'0.10.3',%s,%s,%s)",
            (str(fid), STUDENT_PSEUDO, MELDUNG, status, erstellt, gewechselt),
        )
    sync_conn.commit()
    return str(fid)


def _existiert(conn, fid):
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM feedback WHERE id = %s", (fid,))
        return cur.fetchone() is not None


@pytest.fixture
def lauf(async_engine):
    async def _starten(**kw):
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            return await cleanup_feedback(db, now=JETZT, **kw)

    return _starten


class TestFrist:
    async def test_einen_tag_zu_jung_bleibt(self, sync_conn, lauf):
        fid = _meldung(sync_conn, status="done",
                       gewechselt_vor=timedelta(days=AUFBEWAHRUNG_TAGE - 1))
        ergebnis = await lauf()
        assert ergebnis.geloescht == 0
        assert _existiert(sync_conn, fid)

    async def test_einen_tag_zu_alt_faellt(self, sync_conn, lauf):
        fid = _meldung(sync_conn, status="done",
                       gewechselt_vor=timedelta(days=AUFBEWAHRUNG_TAGE + 1))
        ergebnis = await lauf()
        assert ergebnis.geloescht == 1
        assert not _existiert(sync_conn, fid)

    async def test_alle_drei_abgeschlossenen_zustaende(self, sync_conn, lauf):
        alt = timedelta(days=AUFBEWAHRUNG_TAGE + 5)
        ids = [_meldung(sync_conn, status=s, gewechselt_vor=alt)
               for s in ("done", "declined", "spam")]
        ergebnis = await lauf()
        assert ergebnis.geloescht == 3
        assert not any(_existiert(sync_conn, i) for i in ids)


class TestOffeneBleiben:
    async def test_offene_werden_nie_geloescht(self, sync_conn, lauf):
        """Eine unerledigte Meldung verschwinden zu lassen, räumte ein Versäumnis der
        Sichtung auf, statt es zu melden.

        ⚠️ **Der Zeitstempel ist der Kern des Tests.** Eine nie angefasste Meldung
        hat `status_changed_at = NULL`, und `NULL < stichtag` trifft ohnehin nie zu —
        sie wäre auch ohne Statusfilter sicher. Gefährlich ist die **angefangene**:
        `open → in_progress` setzt den Zeitstempel. Eine Meldung, die seit 200 Tagen
        in Bearbeitung ist, fiele ohne den Statusfilter aus der Tabelle. Beim
        Gegenprüfen blieb der Test genau deshalb zunächst grün.
        """
        ids = [
            _meldung(sync_conn, status="open", erstellt_vor=timedelta(days=900)),
            _meldung(
                sync_conn,
                status="in_progress",
                erstellt_vor=timedelta(days=900),
                gewechselt_vor=timedelta(days=AUFBEWAHRUNG_TAGE + 20),
            ),
        ]
        ergebnis = await lauf()
        assert ergebnis.geloescht == 0
        assert all(_existiert(sync_conn, i) for i in ids)

    async def test_lange_offene_werden_gemeldet(self, sync_conn, lauf):
        _meldung(sync_conn, status="open", erstellt_vor=timedelta(days=HINWEIS_AB_TAGEN + 1))
        assert (await lauf()).lange_offen == 1

    async def test_knapp_unter_der_jahresgrenze_noch_nicht(self, sync_conn, lauf):
        _meldung(sync_conn, status="open", erstellt_vor=timedelta(days=HINWEIS_AB_TAGEN - 1))
        assert (await lauf()).lange_offen == 0


class TestProbelauf:
    async def test_dry_run_zaehlt_nur(self, sync_conn, lauf):
        fid = _meldung(sync_conn, status="done",
                       gewechselt_vor=timedelta(days=AUFBEWAHRUNG_TAGE + 5))
        ergebnis = await lauf(dry_run=True)
        assert ergebnis.faellig == 1
        assert ergebnis.geloescht == 0
        assert _existiert(sync_conn, fid), "Der Probelauf hat gelöscht"


def test_die_fristen_stehen_fest():
    """ADR-011 §6.2 — namentlich, nicht relativ.

    Die Grenzfälle oben rechnen mit `AUFBEWAHRUNG_TAGE ± 1` und prüfen damit die
    Logik der Frist, nicht ihre Länge: Wer die Konstante ändert, verschiebt Aufbau
    **und** Erwartung zugleich, und alles bleibt grün. Diese Zusage hier steht
    absichtlich in Zahlen.
    """
    assert AUFBEWAHRUNG_TAGE == 180
    assert HINWEIS_AB_TAGEN == 365
