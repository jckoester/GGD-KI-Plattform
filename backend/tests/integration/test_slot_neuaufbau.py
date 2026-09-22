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


class TestZweitesHalbjahr:
    """AP2: Das zweite Halbjahr entsteht vorläufig aus dem Raster des ersten."""

    @pytest.fixture
    def erzeuge_hj2(self, async_engine):
        async def _lauf(**kw):
            factory = async_sessionmaker(
                async_engine, class_=AsyncSession, expire_on_commit=False
            )
            async with factory() as db:
                return await generate_slots(db, GRUPPE, 2, cfg=_cfg(), **kw)

        return _lauf

    async def test_faellt_auf_das_muster_des_ersten_zurueck(self, sync_conn, erzeuge_hj2):
        """Für HJ2 ist **kein** Muster hinterlegt — bewusst: Es gibt keins, und ein
        kopiertes sähe wie eine Zusage aus."""
        stats = await erzeuge_hj2(vorlaeufig=True)

        assert stats.used_hj1_fallback is True
        assert stats.created == 1, "Montag der HJ2-Woche"
        zeilen = _slots(sync_conn, halbjahr=2)
        assert len(zeilen) == 1
        assert zeilen[0][4] is True, "Der Termin ist eine Annahme, keine Auskunft"

    async def test_erstes_halbjahr_bleibt_unvorlaeufig(self, sync_conn, erzeuge, erzeuge_hj2):
        await erzeuge()
        await erzeuge_hj2(vorlaeufig=True)

        assert all(z[4] is False for z in _slots(sync_conn, halbjahr=1))
        assert all(z[4] is True for z in _slots(sync_conn, halbjahr=2))

    async def test_zweiter_durchgang_gibt_409_und_laesst_hj1_stehen(
        self, sync_conn, erzeuge, erzeuge_hj2
    ):
        """Bestehende Stunden werden nicht überschrieben — auch nicht die vorläufigen."""
        from fastapi import HTTPException

        await erzeuge()
        await erzeuge_hj2(vorlaeufig=True)
        hj1_vorher = {z[0] for z in _slots(sync_conn, halbjahr=1)}
        hj2_vorher = {z[0] for z in _slots(sync_conn, halbjahr=2)}

        with pytest.raises(HTTPException) as fehler:
            await erzeuge_hj2(vorlaeufig=True)
        assert fehler.value.status_code == 409

        assert {z[0] for z in _slots(sync_conn, halbjahr=1)} == hj1_vorher
        assert {z[0] for z in _slots(sync_conn, halbjahr=2)} == hj2_vorher


class TestAbgleichLegtAn:
    """AP4: Der Stundenplan-Abgleich legt fehlende Termine an — und sie überleben.

    Der zweite Teil ist der Punkt: Ein angelegter Termin mit `source='pattern'` wäre beim
    nächsten „Stunden erzeugen" wieder weg, und der Befund wäre nur verschoben.
    """

    @pytest.fixture
    def abgleichen(self, async_engine):
        async def _lauf(plan):
            from app.calendar.sync import apply_sync

            factory = async_sessionmaker(
                async_engine, class_=AsyncSession, expire_on_commit=False
            )
            async with factory() as db:
                return await apply_sync(db, plan)

        return _lauf

    async def test_termin_entsteht_mit_quellangabe(self, sync_conn, erzeuge, abgleichen):
        from app.calendar.sync import NeuerSlot, SyncPlan

        await erzeuge()
        ziel = date(2026, 1, 8)  # Donnerstag — im Wochenmuster (Montag) nicht vorgesehen
        plan = SyncPlan(anzulegende=[
            NeuerSlot(group_id=GRUPPE, datum=ziel, start_period=6,
                      kategorie="unterricht", notiz=None, external_uid="v1")
        ])
        assert await abgleichen(plan) == 1

        zeilen = [z for z in _slots(sync_conn) if z[1] == ziel]
        assert len(zeilen) == 1
        assert zeilen[0][3] == "import", "Ohne Quellangabe fiele er beim Neuaufbau"

    async def test_er_ueberlebt_den_neuaufbau(self, sync_conn, erzeuge, abgleichen):
        from app.calendar.sync import NeuerSlot, SyncPlan

        await erzeuge()
        ziel = date(2026, 1, 8)
        await abgleichen(SyncPlan(anzulegende=[
            NeuerSlot(group_id=GRUPPE, datum=ziel, start_period=6,
                      kategorie="unterricht", notiz=None, external_uid="v1")
        ]))

        await erzeuge(regenerate=True)

        assert [z for z in _slots(sync_conn) if z[1] == ziel], "Der Termin ist weg"


class TestVorschau:
    """`dry_run` rechnet, ohne zu schreiben (AP5).

    Ohne diese Zahlen ist die Frage „darf ich das Halbjahr neu aufbauen" nicht zu
    beantworten — und genau davor stand bisher nur eine Ja/Nein-Rückfrage.
    """

    async def test_zaehlt_ohne_zu_schreiben(self, sync_conn, erzeuge):
        await erzeuge()
        vorher = {z[0] for z in _slots(sync_conn)}

        stats = await erzeuge(regenerate=True, dry_run=True)

        assert stats.created == len(vorher)
        assert {z[0] for z in _slots(sync_conn)} == vorher, "Die Vorschau hat geschrieben"

    async def test_nennt_umhaengen_und_parkplatz(self, sync_conn, erzeuge):
        """Mit Inhalt und weniger Terminen: Die Vorschau sagt, was übrig bliebe."""
        await erzeuge()
        sync_conn.rollback()
        with sync_conn.cursor() as cur:
            cur.execute(
                "UPDATE lesson_slots SET thema = 'A' WHERE group_id = %s", (GRUPPE,)
            )
            # Muster halbieren: nur noch jede zweite Stunde.
            cur.execute(
                "UPDATE group_week_patterns SET weekday = 4 WHERE group_id = %s", (GRUPPE,)
            )
        sync_conn.commit()
        geparkt_vorher = _lese_parkplatz(sync_conn)

        stats = await erzeuge(regenerate=True, dry_run=True)

        assert stats.umgehaengt > 0
        assert _lese_parkplatz(sync_conn) == geparkt_vorher, "Die Vorschau hat geparkt"
        assert stats.meldungen, "Ohne Sätze ist die Vorschau keine Auskunft"


def _lese_parkplatz(conn):
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM parked_lesson_content WHERE group_id = %s", (GRUPPE,)
        )
        return cur.fetchone()[0]

