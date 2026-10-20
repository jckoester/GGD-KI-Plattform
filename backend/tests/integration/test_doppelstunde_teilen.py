"""Doppelstunde teilen und wieder zusammenlegen (0.19, Schritt 3).

Gegen die Datenbank: Die Zusagen stecken in Zeilen — wer welche Felder behält, was der
Neuaufbau aus dem Wochenmuster stehen lässt, und dass ein Entwurf nur an einem Termin hängt.
"""
import uuid
from datetime import date

import psycopg2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.planning.calendar import SchoolYearConfig
from app.planning.slot_generator import generate_slots
from tests.integration.conftest import TEACHER1_PSEUDO

GRUPPE = 990087
MONTAG = date(2026, 1, 5)


def _cfg() -> SchoolYearConfig:
    """Eine Unterrichtswoche je Halbjahr — wie in `test_slot_neuaufbau.py`."""
    return SchoolYearConfig(
        schuljahr="2026/27", beginn=date(2026, 1, 5), ende=date(2026, 1, 16),
        halbjahreswechsel=date(2026, 1, 12), ferien=[], feiertage=[], unterrichtsfreie_tage=[],
    )


@pytest.fixture(scope="module")
def conn(db_url, run_migrations):
    c = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    yield c
    c.close()


@pytest.fixture(autouse=True)
def bestand(conn):
    """Gruppe mit Lehrkraft und Wochenmuster: Montag, 1.–2. Stunde als Doppelstunde."""
    def raeumen():
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lesson_slots WHERE group_id = %s", (GRUPPE,))
            cur.execute("DELETE FROM slot_plan_snapshots WHERE group_id = %s", (GRUPPE,))
            cur.execute("DELETE FROM group_week_patterns WHERE group_id = %s", (GRUPPE,))
            cur.execute("DELETE FROM context_nodes WHERE write_scope_group_id = %s", (GRUPPE,))
            cur.execute("DELETE FROM group_memberships WHERE group_id = %s", (GRUPPE,))
            cur.execute("DELETE FROM groups WHERE id = %s", (GRUPPE,))
        conn.commit()

    raeumen()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO groups (id, name, slug, type) VALUES "
                    "(%s, 'Teilen-Testgruppe', 'teilen-test', 'teaching_group')", (GRUPPE,))
        cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                    "VALUES (%s, %s, 'teacher', 'eigen')", (GRUPPE, TEACHER1_PSEUDO))
        cur.execute("INSERT INTO group_week_patterns (group_id, halbjahr, weekday, start_period, "
                    "periods, rhythmus) VALUES (%s, 1, 0, 1, 2, 'woechentlich')", (GRUPPE,))
    conn.commit()
    yield
    raeumen()


@pytest.fixture
def erzeuge(async_engine):
    async def _lauf(**kw):
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            return await generate_slots(db, GRUPPE, 1, cfg=_cfg(), **kw)
    return _lauf


def _knoten(conn, titel, art):
    kid = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO context_nodes (id, category, content_type, title, owner_pseudonym, "
            "read_scope, write_scope, read_scope_group_id, write_scope_group_id) "
            "VALUES (%s, 'artifact', %s, %s, %s, 'group', 'group', %s, %s)",
            (kid, art, titel, TEACHER1_PSEUDO, GRUPPE, GRUPPE),
        )
    conn.commit()
    return kid


def _slots(conn):
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, start_period, periods, geteilt, kategorie, ue_node_id, stunde_node_id, "
            "thema, source FROM lesson_slots WHERE group_id = %s ORDER BY date, start_period",
            (GRUPPE,))
        spalten = ("id", "sp", "periods", "geteilt", "kategorie", "ue", "stunde", "thema", "source")
        return [dict(zip(spalten, (str(z[0]), *z[1:5], *(str(x) if x else None for x in z[5:7]), *z[7:])))
                for z in cur.fetchall()]


def _setze(conn, sid, **felder):
    with conn.cursor() as cur:
        for feld, wert in felder.items():
            cur.execute(f"UPDATE lesson_slots SET {feld} = %s WHERE id = %s", (wert, sid))
    conn.commit()


async def _doppelstunde(conn, erzeuge):
    await erzeuge()
    montag = [s for s in _slots(conn)]
    assert montag[0]["periods"] == 2, montag
    return montag[0]["id"]


class TestTeilen:
    async def test_entwurf_und_thema_an_der_ersten_einheit_und_ausfall_an_beiden(
        self, conn, erzeuge, test_client, auth_headers
    ):
        sid = await _doppelstunde(conn, erzeuge)
        ue, stunde = _knoten(conn, "Brüche", "unterrichtseinheit"), _knoten(conn, "Kürzen", "unterrichtsstunde")
        _setze(conn, sid, ue_node_id=ue, stunde_node_id=stunde, thema="Kürzen",
               kategorie="ausfall", ausfall_herkunft="stundenplan", ausfall_vorher="unterricht")

        antwort = await test_client.post(f"/planning/slots/{sid}/teilen", headers=auth_headers)
        assert antwort.status_code == 200, antwort.text
        assert [s["start_period"] for s in antwort.json()["slots"]] == [1, 2]

        erste, zweite = _slots(conn)
        assert erste["id"] == sid
        assert (erste["periods"], erste["geteilt"], erste["stunde"], erste["thema"]) == (1, True, stunde, "Kürzen")
        assert (zweite["sp"], zweite["periods"], zweite["geteilt"]) == (2, 1, True)
        assert (zweite["stunde"], zweite["thema"]) == (None, None)
        assert zweite["ue"] == ue and zweite["source"] == erste["source"] == "pattern"
        assert erste["kategorie"] == zweite["kategorie"] == "ausfall"

    async def test_nur_doppelstunden(self, conn, erzeuge, test_client, auth_headers):
        sid = await _doppelstunde(conn, erzeuge)
        await test_client.post(f"/planning/slots/{sid}/teilen", headers=auth_headers)
        antwort = await test_client.post(f"/planning/slots/{sid}/teilen", headers=auth_headers)
        assert antwort.status_code == 409

    async def test_nur_lehrkraefte_der_gruppe(self, conn, erzeuge, test_client, auth_headers_teacher2):
        sid = await _doppelstunde(conn, erzeuge)
        antwort = await test_client.post(f"/planning/slots/{sid}/teilen", headers=auth_headers_teacher2)
        assert antwort.status_code == 403
        assert len(_slots(conn)) == 1

    async def test_veralteter_stand_gibt_409(self, conn, erzeuge, test_client, auth_headers):
        sid = await _doppelstunde(conn, erzeuge)
        antwort = await test_client.post(f"/planning/slots/{sid}/teilen", headers=auth_headers,
                                         json={"expected_updated_at": "2020-01-01T00:00:00Z"})
        assert antwort.status_code == 409


class TestNeuaufbau:
    async def test_laesst_die_teilung_stehen(self, conn, erzeuge, test_client, auth_headers):
        """Bis 0.19 prüfte der Generator nur die erste Stunde eines verschonten Termins — und
        ein Muster-Slot fiel ohnehin. Die Teilung wäre beim nächsten Neuaufbau weg gewesen."""
        sid = await _doppelstunde(conn, erzeuge)
        await test_client.post(f"/planning/slots/{sid}/teilen", headers=auth_headers)
        vorher = {s["id"] for s in _slots(conn)}

        stats = await erzeuge(regenerate=True)

        # Das Halbjahr hat genau diesen einen Montag: Es bleiben die beiden Hälften, und keine
        # Doppelstunde aus dem Muster legt sich darüber.
        nachher = _slots(conn)
        assert {s["id"] for s in nachher} == vorher, nachher
        assert stats.verschont == 2

    async def test_importierte_zweite_stunde_verhindert_die_doppelstunde(self, conn, erzeuge):
        """Dieselbe Regel ohne Teilen: eine importierte Einzelstunde in der 2. Stunde."""
        with conn.cursor() as cur:
            cur.execute("INSERT INTO lesson_slots (group_id, date, start_period, periods, halbjahr, "
                        "kategorie, source) VALUES (%s, %s, 2, 1, 1, 'unterricht', 'import')",
                        (GRUPPE, MONTAG))
        conn.commit()
        await erzeuge(regenerate=True)
        montag = [s for s in _slots(conn) if s["sp"] in (1, 2)]
        assert not any(s["periods"] == 2 and s["sp"] == 1 for s in montag[:1]), montag


class TestZusammenlegen:
    async def test_von_der_zweiten_haelfte_aus(self, conn, erzeuge, test_client, auth_headers):
        sid = await _doppelstunde(conn, erzeuge)
        await test_client.post(f"/planning/slots/{sid}/teilen", headers=auth_headers)
        zweite = _slots(conn)[1]["id"]

        antwort = await test_client.post(f"/planning/slots/{zweite}/zusammenlegen", headers=auth_headers)
        assert antwort.status_code == 200, antwort.text
        zeilen = [s for s in _slots(conn) if s["sp"] in (1, 2)]
        assert [(s["id"], s["periods"], s["geteilt"]) for s in zeilen][:1] == [(sid, 2, False)]
        assert zweite not in {s["id"] for s in _slots(conn)}

    async def test_eigener_inhalt_der_zweiten_haelfte_verhindert_es(
        self, conn, erzeuge, test_client, auth_headers
    ):
        sid = await _doppelstunde(conn, erzeuge)
        await test_client.post(f"/planning/slots/{sid}/teilen", headers=auth_headers)
        zweite = _slots(conn)[1]["id"]
        _setze(conn, zweite, thema="Klassenarbeit")

        antwort = await test_client.post(f"/planning/slots/{sid}/zusammenlegen", headers=auth_headers)
        assert antwort.status_code == 409
        assert "2. Stunde" in antwort.json()["detail"]
        assert len([s for s in _slots(conn) if s["geteilt"]]) == 2

    async def test_ungeteilte_stunde(self, conn, erzeuge, test_client, auth_headers):
        sid = await _doppelstunde(conn, erzeuge)
        antwort = await test_client.post(f"/planning/slots/{sid}/zusammenlegen", headers=auth_headers)
        assert antwort.status_code == 409


class TestEinEntwurfEinTermin:
    async def test_index_verbietet_zwei_termine(self, conn, erzeuge):
        """`get_lesson` liest den Termin mit `scalar_one_or_none` — zwei brächen es (0087)."""
        await erzeuge()
        with conn.cursor() as cur:
            cur.execute("INSERT INTO lesson_slots (group_id, date, start_period, periods, halbjahr, "
                        "kategorie, source) VALUES (%s, %s, 5, 1, 1, 'unterricht', 'manual')",
                        (GRUPPE, MONTAG))
        conn.commit()
        stunde = _knoten(conn, "Doppelt", "unterrichtsstunde")
        ids = [s["id"] for s in _slots(conn)]
        _setze(conn, ids[0], stunde_node_id=stunde)
        with pytest.raises(psycopg2.errors.UniqueViolation):
            _setze(conn, ids[1], stunde_node_id=stunde)
        conn.rollback()


class TestWiederherstellen:
    async def test_snapshot_loest_den_entwurf_an_einem_neueren_termin(
        self, conn, erzeuge, test_client, auth_headers
    ):
        """Der Snapshot kennt die zweite Hälfte nicht. Hängt der Entwurf inzwischen dort und
        stellt der Snapshot ihn am alten Termin wieder her, gewinnt der Snapshot — sonst
        scheiterte das Wiederherstellen am Commit (ein Entwurf, ein Termin)."""
        sid = await _doppelstunde(conn, erzeuge)
        stunde = _knoten(conn, "Wandert", "unterrichtsstunde")
        _setze(conn, sid, stunde_node_id=stunde)
        # Ein Wiederherstellungspunkt mit dem Entwurf an der Doppelstunde.
        assert (await test_client.patch(f"/planning/slots/{sid}", headers=auth_headers,
                                         json={"thema": "vorher"})).status_code == 200
        await test_client.patch(f"/planning/slots/{sid}", headers=auth_headers, json={"ue_node_id": None})
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM slot_plan_snapshots WHERE group_id = %s "
                        "ORDER BY created_at DESC LIMIT 1", (GRUPPE,))
            snapshot = str(cur.fetchone()[0])

        await test_client.post(f"/planning/slots/{sid}/teilen", headers=auth_headers)
        zweite = _slots(conn)[1]["id"]
        _setze(conn, sid, stunde_node_id=None)
        _setze(conn, zweite, stunde_node_id=stunde)

        antwort = await test_client.post(f"/planning/snapshots/{snapshot}/restore", headers=auth_headers)
        assert antwort.status_code == 200, antwort.text
        erste, zweite_neu = _slots(conn)
        assert (erste["stunde"], zweite_neu["stunde"]) == (stunde, None)
