"""Was der Neuaufbau eines Halbjahres anfasst — und der Löschpfad dazu (AP1, 22.09.2026).

Gegen die Datenbank, nicht mit Mocks: Die Zusage steckt im `WHERE` des `DELETE` — welche
Zeile es trifft und welche nicht. Ein Mock zeigte nur, dass *irgendein* Löschbefehl
gebaut wurde.

**Der Befund dahinter.** Bis zum 22.09.2026 löschte `regenerate=True` das ganze Halbjahr.
Ein vom Stundenplan-Abgleich angelegter Termin verschwand damit beim nächsten Erzeugen
wieder — und weil Slots sich nicht einzeln löschen ließen, war das gleichzeitig der
einzige Weg, einen falschen Termin loszuwerden. Beides ändert sich hier gemeinsam.
"""
import uuid
from datetime import date

import psycopg2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.planning.calendar import SchoolYearConfig
from app.planning.slot_generator import generate_slots
from tests.integration.conftest import TEACHER1_PSEUDO, TEACHER2_PSEUDO

GRUPPE = 990002


def _cfg() -> SchoolYearConfig:
    """Ein Mini-Schuljahr: eine Unterrichtswoche je Halbjahr, deterministisch."""
    return SchoolYearConfig(
        schuljahr="2026/27",
        beginn=date(2026, 1, 5),          # Montag
        ende=date(2026, 1, 16),           # Freitag der zweiten Woche
        halbjahreswechsel=date(2026, 1, 12),
        ferien=[],
        feiertage=[],
        unterrichtsfreie_tage=[],
    )


@pytest.fixture(scope="module")
def sync_conn(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def bestand(sync_conn):
    """Eine eigene Gruppe mit Lehrkraft und einem Wochenmuster (Montag, 1. Stunde)."""
    def raeumen():
        sync_conn.rollback()
        with sync_conn.cursor() as cur:
            cur.execute("DELETE FROM lesson_slots WHERE group_id = %s", (GRUPPE,))
            cur.execute("DELETE FROM slot_plan_snapshots WHERE group_id = %s", (GRUPPE,))
            cur.execute("DELETE FROM group_week_patterns WHERE group_id = %s", (GRUPPE,))
            cur.execute("DELETE FROM group_memberships WHERE group_id = %s", (GRUPPE,))
            cur.execute("DELETE FROM groups WHERE id = %s", (GRUPPE,))
        sync_conn.commit()

    raeumen()
    with sync_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO groups (id, name, slug, type)"
            " VALUES (%s,'Neuaufbau-Testgruppe','neuaufbau-test','teaching_group')",
            (GRUPPE,),
        )
        cur.execute(
            "INSERT INTO group_memberships (group_id, pseudonym, role_in_group)"
            " VALUES (%s,%s,'teacher')",
            (GRUPPE, TEACHER1_PSEUDO),
        )
        cur.execute(
            "INSERT INTO group_week_patterns (group_id, halbjahr, weekday, start_period,"
            " periods, rhythmus) VALUES (%s,1,0,1,1,'woechentlich')",
            (GRUPPE,),
        )
    sync_conn.commit()
    yield
    raeumen()


def _slot(sync_conn, *, datum, start_period=1, source, thema=None, halbjahr=1):
    sid = uuid.uuid4()
    sync_conn.rollback()
    with sync_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO lesson_slots (id, group_id, date, start_period, periods,"
            " halbjahr, kategorie, source, thema)"
            " VALUES (%s,%s,%s,%s,1,%s,'unterricht',%s,%s)",
            (str(sid), GRUPPE, datum, start_period, halbjahr, source, thema),
        )
    sync_conn.commit()
    return str(sid)


def _slots(conn, *, halbjahr=1):
    """Die Slots der Testgruppe. Die `id` kommt **immer als Zeichenkette** zurück.

    ⚠️ Nicht Kosmetik, sondern eine Kopplung zwischen Testdateien: `test_ks_phase2.py`
    ruft `psycopg2.extras.register_uuid(conn)` — die Verbindung landet dabei im ersten
    Parameter `oids`, nicht in `conn_or_curs`, und der Adapter wird damit **global**
    registriert statt für diese eine Verbindung. Danach liefert psycopg2 `uuid`-Spalten
    als `uuid.UUID` statt als `str`. Allein lief diese Datei grün, im Gesamtlauf nicht.
    """
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, date, start_period, source, vorlaeufig FROM lesson_slots"
            " WHERE group_id = %s AND halbjahr = %s ORDER BY date, start_period",
            (GRUPPE, halbjahr),
        )
        return [(str(z[0]), *z[1:]) for z in cur.fetchall()]


def _existiert(conn, sid):
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM lesson_slots WHERE id = %s", (sid,))
        return cur.fetchone() is not None


@pytest.fixture
def erzeuge(async_engine):
    async def _lauf(**kw):
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            return await generate_slots(db, GRUPPE, 1, cfg=_cfg(), **kw)

    return _lauf


class TestNeuaufbau:
    async def test_musterslots_fallen(self, sync_conn, erzeuge):
        await erzeuge()
        vorher = {z[0] for z in _slots(sync_conn)}
        assert len(vorher) == 1

        await erzeuge(regenerate=True)
        nachher = {z[0] for z in _slots(sync_conn)}
        assert len(nachher) == 1
        assert nachher != vorher, "Der Muster-Slot hätte neu entstehen müssen"

    async def test_importslot_bleibt(self, sync_conn, erzeuge):
        """Er trägt eine Quellangabe aus dem Stundenplan — die reproduziert kein Muster."""
        sid = _slot(sync_conn, datum=date(2026, 1, 6), source="import")
        stats = await erzeuge(regenerate=True)
        assert _existiert(sync_conn, sid)
        assert stats.verschont == 1

    async def test_handslot_bleibt(self, sync_conn, erzeuge):
        """Er trägt eine Entscheidung — der Sync fasst ihn ohnehin nie an (UP-8)."""
        sid = _slot(sync_conn, datum=date(2026, 1, 7), source="manual")
        await erzeuge(regenerate=True)
        assert _existiert(sync_conn, sid)

    async def test_belegter_termin_erzeugt_keine_dublette(self, sync_conn, erzeuge):
        """F4: Auf demselben Termin entfällt die Musterzeile, nicht der verschonte Slot."""
        # Montag, 1. Stunde — genau die Zeile des Wochenmusters.
        sid = _slot(sync_conn, datum=date(2026, 1, 5), source="import")
        await erzeuge(regenerate=True)

        zeilen = _slots(sync_conn)
        assert len(zeilen) == 1, f"Dublette: {zeilen}"
        assert zeilen[0][0] == sid
        assert zeilen[0][3] == "import"


class TestVorlaeufig:
    async def test_kennzeichen_landet_in_der_datenbank(self, sync_conn, erzeuge):
        await erzeuge(vorlaeufig=True)
        assert all(z[4] is True for z in _slots(sync_conn))

    async def test_ohne_angabe_nicht_vorlaeufig(self, sync_conn, erzeuge):
        await erzeuge()
        assert all(z[4] is False for z in _slots(sync_conn))


class TestLoeschen:
    async def test_leerer_importslot_geht(self, sync_conn, test_client, auth_headers):
        sid = _slot(sync_conn, datum=date(2026, 1, 6), source="import")
        antwort = await test_client.delete(f"/planning/slots/{sid}", headers=auth_headers)
        assert antwort.status_code == 200, antwort.text
        assert not _existiert(sync_conn, sid)

    async def test_slot_mit_inhalt_gibt_409(self, sync_conn, test_client, auth_headers):
        """Eine Stunde mit Planung zu löschen, um einen Termin loszuwerden, wirft die
        Arbeit weg — erst den Inhalt verschieben."""
        sid = _slot(sync_conn, datum=date(2026, 1, 6), source="import", thema="Bruchrechnen")
        antwort = await test_client.delete(f"/planning/slots/{sid}", headers=auth_headers)
        assert antwort.status_code == 409
        assert _existiert(sync_conn, sid)

    async def test_musterslot_gibt_409(self, sync_conn, test_client, auth_headers, erzeuge):
        """Er wäre beim nächsten Erzeugen wieder da — die Korrektur ist das Muster."""
        await erzeuge()
        sid = _slots(sync_conn)[0][0]
        antwort = await test_client.delete(f"/planning/slots/{sid}", headers=auth_headers)
        assert antwort.status_code == 409
        assert "Wochenmuster" in antwort.json()["detail"]
        assert _existiert(sync_conn, sid)

    async def test_fremde_lehrkraft_gibt_403(
        self, sync_conn, test_client, auth_headers_teacher2
    ):
        sid = _slot(sync_conn, datum=date(2026, 1, 6), source="import")
        antwort = await test_client.delete(
            f"/planning/slots/{sid}", headers=auth_headers_teacher2
        )
        assert antwort.status_code == 403
        assert _existiert(sync_conn, sid)

    async def test_unbekannte_id_gibt_404(self, test_client, auth_headers):
        antwort = await test_client.delete(
            f"/planning/slots/{uuid.uuid4()}", headers=auth_headers
        )
        assert antwort.status_code == 404
