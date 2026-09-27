"""Das Umhängen gegen die Datenbank (AP3, 22.09.2026).

Hier zählt, was `plane_umhaengen` nicht beantworten kann: die **Reihenfolge von Schreiben
und Löschen** und die Zusage, dass dabei kein Inhalt verlorengeht. Gemessen wird sie als
Summe aus inhaltstragenden Slots **plus** Parkplatz-Einträgen — sonst wäre sie durch das
Parken trivial erfüllt.
"""
import uuid
from datetime import date

import psycopg2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.planning.umhaengen import (
    AlterSlot,
    NeuerTermin,
    plane_umhaengen,
    wende_umhaengen_an,
)
from tests.integration.conftest import TEACHER1_PSEUDO, TEACHER2_PSEUDO

GRUPPE = 990003
MO, DI, MI = date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4)
MO2 = date(2026, 3, 9)


@pytest.fixture(scope="module")
def sync_conn(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def gruppe(sync_conn):
    def raeumen():
        sync_conn.rollback()
        with sync_conn.cursor() as cur:
            cur.execute("DELETE FROM parked_lesson_content WHERE group_id = %s", (GRUPPE,))
            cur.execute("DELETE FROM lesson_slots WHERE group_id = %s", (GRUPPE,))
            cur.execute("DELETE FROM slot_plan_snapshots WHERE group_id = %s", (GRUPPE,))
            cur.execute("DELETE FROM group_memberships WHERE group_id = %s", (GRUPPE,))
            cur.execute("DELETE FROM groups WHERE id = %s", (GRUPPE,))
        sync_conn.commit()

    raeumen()
    with sync_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO groups (id, name, slug, type)"
            " VALUES (%s,'Umhaenge-Testgruppe','umhaenge-test','teaching_group')",
            (GRUPPE,),
        )
        cur.execute(
            "INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft)"
            " VALUES (%s,%s,'teacher','eigen')",
            (GRUPPE, TEACHER1_PSEUDO),
        )
    sync_conn.commit()
    yield
    raeumen()


def _slot(sync_conn, datum, *, thema=None, kategorie="unterricht", periods=1, source="pattern"):
    sid = uuid.uuid4()
    sync_conn.rollback()
    with sync_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO lesson_slots (id, group_id, date, start_period, periods,"
            " halbjahr, kategorie, source, thema) VALUES (%s,%s,%s,1,%s,2,%s,%s,%s)",
            (str(sid), GRUPPE, datum, periods, kategorie, source, thema),
        )
    sync_conn.commit()
    return sid


def _lese(conn, sql, *werte):
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(sql, werte)
        return cur.fetchall()


def _inhalt_gesamt(conn):
    """Inhaltstragende Slots **plus** Parkplatz-Einträge.

    Die eigentliche Zusage lautet „kein Inhalt geht verloren". Nur die Slots zu zählen
    wäre erfüllbar, indem man alles parkt; nur den Parkplatz zu zählen, indem man alles
    zuordnet. Die Summe ist die Aussage.
    """
    slots = _lese(
        conn,
        "SELECT count(*) FROM lesson_slots WHERE group_id = %s"
        " AND (ue_node_id IS NOT NULL OR stunde_node_id IS NOT NULL OR thema IS NOT NULL)",
        GRUPPE,
    )[0][0]
    geparkt = _lese(
        conn, "SELECT count(*) FROM parked_lesson_content WHERE group_id = %s", GRUPPE
    )[0][0]
    return slots + geparkt


def _alte(sync_conn):
    """Die vorhandenen Muster-Slots als `AlterSlot` — so übergibt sie der Generator."""
    zeilen = _lese(
        sync_conn,
        "SELECT id, date, start_period, periods, kategorie, pinned, thema FROM lesson_slots"
        " WHERE group_id = %s AND source = 'pattern' ORDER BY date",
        GRUPPE,
    )
    return [
        AlterSlot(
            id=z[0], datum=z[1], start_period=z[2], periods=z[3],
            kategorie=z[4], pinned=z[5], thema=z[6],
        )
        for z in zeilen
    ]


@pytest.fixture
def anwenden(async_engine):
    async def _lauf(plan):
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            return await wende_umhaengen_an(
                db, GRUPPE, 2, plan, created_by=TEACHER1_PSEUDO
            )

    return _lauf


class TestKeinInhaltVerloren:
    async def test_summe_bleibt_gleich_bei_weniger_terminen(self, sync_conn, anwenden):
        _slot(sync_conn, MO, thema="A")
        _slot(sync_conn, DI, thema="B")
        _slot(sync_conn, MI, thema="C")
        vorher = _inhalt_gesamt(sync_conn)
        assert vorher == 3

        plan = plane_umhaengen(_alte(sync_conn), [NeuerTermin(MO2, 1, 1)])
        await anwenden(plan)

        assert _inhalt_gesamt(sync_conn) == vorher

    async def test_alte_slots_sind_weg(self, sync_conn, anwenden):
        alt_ids = {_slot(sync_conn, MO, thema="A"), _slot(sync_conn, DI, thema="B")}
        plan = plane_umhaengen(_alte(sync_conn), [NeuerTermin(MO2, 1, 1), NeuerTermin(DI, 1, 1)])
        await anwenden(plan)

        uebrig = {z[0] for z in _lese(sync_conn, "SELECT id FROM lesson_slots WHERE group_id = %s", GRUPPE)}
        assert not (uebrig & alt_ids), "Alte Slots stehen noch da — Dubletten"

    async def test_snapshot_liegt_richtig(self, sync_conn, anwenden):
        """`reason='regeneration'` — daran findet der vorhandene Reflow-Kontext ihn."""
        _slot(sync_conn, MO, thema="A")
        plan = plane_umhaengen(_alte(sync_conn), [NeuerTermin(MO2, 1, 1)])
        await anwenden(plan)

        gruende = [z[0] for z in _lese(
            sync_conn, "SELECT reason FROM slot_plan_snapshots WHERE group_id = %s", GRUPPE
        )]
        assert gruende == ["regeneration"]


class TestUmfangUndParkplatz:
    async def test_abweichender_umfang_wird_markiert(self, sync_conn, anwenden):
        _slot(sync_conn, MO, thema="Versuchsreihe", periods=2)
        plan = plane_umhaengen(_alte(sync_conn), [NeuerTermin(MO2, 1, 1)])
        await anwenden(plan)

        zeilen = _lese(
            sync_conn,
            "SELECT thema, periods, anpassung_noetig FROM lesson_slots WHERE group_id = %s",
            GRUPPE,
        )
        assert zeilen == [("Versuchsreihe", 1, True)]

    async def test_ueberhang_landet_mit_herkunft_auf_dem_parkplatz(self, sync_conn, anwenden):
        _slot(sync_conn, MO, thema="A")
        _slot(sync_conn, DI, thema="B")
        plan = plane_umhaengen(_alte(sync_conn), [NeuerTermin(MO2, 1, 1)])
        await anwenden(plan)

        geparkt = _lese(
            sync_conn,
            "SELECT thema, herkunft_datum, halbjahr FROM parked_lesson_content"
            " WHERE group_id = %s",
            GRUPPE,
        )
        assert geparkt == [("B", DI, 2)]


class TestFixpunktOhneTermin:
    async def test_bleibt_stehen_und_wechselt_auf_manual(self, sync_conn, anwenden):
        """E5 und E6 zusammen: Sie bloß zu melden und den Slot zu löschen hätte die
        Klassenarbeit verschwinden lassen. `manual` heißt danach: von Hand gepflegt,
        nicht vom Muster — der nächste Neuaufbau lässt sie stehen."""
        ka = _slot(sync_conn, DI, thema="Klassenarbeit", kategorie="pruefung")
        plan = plane_umhaengen(_alte(sync_conn), [NeuerTermin(MO2, 1, 1)])
        assert len(plan.nicht_zuordenbar) == 1
        await anwenden(plan)

        zeilen = _lese(
            sync_conn,
            "SELECT thema, date, source, anpassung_noetig FROM lesson_slots"
            " WHERE id = %s", str(ka),
        )
        assert zeilen == [("Klassenarbeit", DI, "manual", True)]


class TestParkplatzEndpunkte:
    async def test_liste_nennt_herkunft_und_ueberhang(
        self, sync_conn, anwenden, test_client, auth_headers
    ):
        _slot(sync_conn, MO, thema="A")
        _slot(sync_conn, DI, thema="B")
        plan = plane_umhaengen(_alte(sync_conn), [NeuerTermin(MO2, 1, 1)])
        await anwenden(plan)

        antwort = await test_client.get(
            f"/planning/groups/{GRUPPE}/parkplatz", headers=auth_headers
        )
        assert antwort.status_code == 200, antwort.text
        koerper = antwort.json()
        assert len(koerper["items"]) == 1
        assert koerper["items"][0]["thema"] == "B"
        assert koerper["items"][0]["herkunft_datum"] == DI.isoformat()
        assert "ueberhang" in koerper

    async def test_fremde_lehrkraft_sieht_den_parkplatz_nicht(
        self, test_client, auth_headers_teacher2
    ):
        antwort = await test_client.get(
            f"/planning/groups/{GRUPPE}/parkplatz", headers=auth_headers_teacher2
        )
        assert antwort.status_code == 403

    async def test_verwerfen_laesst_den_stundenentwurf_stehen(
        self, sync_conn, test_client, auth_headers
    ):
        """E11: Verworfen wird die Zusage, nicht der Entwurf."""
        knoten = uuid.uuid4()
        eintrag = uuid.uuid4()
        sync_conn.rollback()
        with sync_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO context_nodes (id, category, content_type, title,"
                " read_scope, write_scope, status)"
                " VALUES (%s,'artifact','unterrichtsstunde','Entwurf','private','private','active')",
                (str(knoten),),
            )
            cur.execute(
                "INSERT INTO parked_lesson_content (id, group_id, halbjahr,"
                " herkunft_datum, stunde_node_id, thema) VALUES (%s,%s,2,%s,%s,'A')",
                (str(eintrag), GRUPPE, DI, str(knoten)),
            )
        sync_conn.commit()

        antwort = await test_client.delete(
            f"/planning/parkplatz/{eintrag}", headers=auth_headers
        )
        assert antwort.status_code == 200

        assert _lese(sync_conn, "SELECT count(*) FROM parked_lesson_content WHERE id = %s",
                     str(eintrag))[0][0] == 0
        assert _lese(sync_conn, "SELECT count(*) FROM context_nodes WHERE id = %s",
                     str(knoten))[0][0] == 1, "Der Entwurf wurde mitgelöscht"

        sync_conn.rollback()
        with sync_conn.cursor() as cur:
            cur.execute("DELETE FROM context_nodes WHERE id = %s", (str(knoten),))
        sync_conn.commit()

    async def test_unbekannter_eintrag_gibt_404(self, test_client, auth_headers):
        antwort = await test_client.delete(
            f"/planning/parkplatz/{uuid.uuid4()}", headers=auth_headers
        )
        assert antwort.status_code == 404


class TestZurueckInDenPlan:
    """Der Gegenweg: `unpark_content` holt geparkten Inhalt auf einen freien Termin.

    Geprüft wird über `apply_operations` — einen HTTP-Endpunkt für Plan-Operationen gibt
    es nicht, sie laufen über das Chat-Werkzeug `apply_plan_operations`. Deshalb kommt
    die Absage als Fehlerliste zurück und nicht als Statuscode.
    """

    @pytest.fixture
    def parkplatz_eintrag(self, sync_conn):
        def _anlegen(thema="B", datum=DI):
            eid = uuid.uuid4()
            sync_conn.rollback()
            with sync_conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO parked_lesson_content (id, group_id, halbjahr,"
                    " herkunft_datum, thema) VALUES (%s,%s,2,%s,%s)",
                    (str(eid), GRUPPE, datum, thema),
                )
            sync_conn.commit()
            return eid

        return _anlegen

    @pytest.fixture
    def ausfuehren(self, async_engine):
        async def _lauf(ops):
            from app.planning.operations import apply_operations, parse_operations

            factory = async_sessionmaker(
                async_engine, class_=AsyncSession, expire_on_commit=False
            )
            async with factory() as db:
                return await apply_operations(
                    db, GRUPPE, parse_operations(ops),
                    summary="Test", created_by=TEACHER1_PSEUDO,
                )

        return _lauf

    async def test_leerer_termin_nimmt_den_inhalt_auf(
        self, sync_conn, parkplatz_eintrag, ausfuehren
    ):
        ziel = _slot(sync_conn, MO2)
        eintrag = parkplatz_eintrag()

        ergebnis = await ausfuehren([
            {"op": "unpark_content", "parkplatz_id": str(eintrag), "to_slot_id": str(ziel)}
        ])
        assert ergebnis.errors == []
        assert ergebnis.applied == 1

        zeilen = _lese(
            sync_conn,
            "SELECT thema, anpassung_noetig FROM lesson_slots WHERE id = %s", str(ziel)
        )
        assert zeilen == [("B", True)], "Neuer Termin — der Inhalt gehört geprüft"
        assert _lese(
            sync_conn, "SELECT count(*) FROM parked_lesson_content WHERE id = %s", str(eintrag)
        )[0][0] == 0

    async def test_belegter_termin_wird_abgewiesen(
        self, sync_conn, parkplatz_eintrag, ausfuehren
    ):
        ziel = _slot(sync_conn, MO2, thema="schon da")
        eintrag = parkplatz_eintrag()

        ergebnis = await ausfuehren([
            {"op": "unpark_content", "parkplatz_id": str(eintrag), "to_slot_id": str(ziel)}
        ])
        assert ergebnis.applied == 0
        assert any("belegt" in f for f in ergebnis.errors)
        assert any(str(MO2) in f for f in ergebnis.errors), "Das Datum gehört in die Absage"

        # Nichts halb geändert.
        assert _lese(sync_conn, "SELECT thema FROM lesson_slots WHERE id = %s",
                     str(ziel)) == [("schon da",)]
        assert _lese(
            sync_conn, "SELECT count(*) FROM parked_lesson_content WHERE id = %s", str(eintrag)
        )[0][0] == 1

    async def test_unbekannter_eintrag_wird_abgewiesen(self, sync_conn, ausfuehren):
        ziel = _slot(sync_conn, MO2)
        ergebnis = await ausfuehren([
            {"op": "unpark_content", "parkplatz_id": str(uuid.uuid4()),
             "to_slot_id": str(ziel)}
        ])
        assert ergebnis.applied == 0
        assert any("nicht gefunden" in f for f in ergebnis.errors)


class TestKategorieBleibtAmTermin:
    """Kategorie und `pinned` beschreiben den Termin, nicht den Inhalt.

    Aufgefallen am 22.09.2026 durch `test_patch_kategorie_auto_snapshot_restore`: Die
    erste Fassung ließ die Kategorie mitwandern. Eine ausgefallene Stunde machte damit
    aus einem frischen Termin des neuen Musters einen Ausfall — abgesagt hatte den
    niemand.
    """

    async def test_ausfall_wandert_nicht_mit(self, sync_conn, anwenden):
        _slot(sync_conn, MO, thema="A", kategorie="ausfall")
        plan = plane_umhaengen(_alte(sync_conn), [NeuerTermin(MO2, 1, 1)])
        await anwenden(plan)

        assert _lese(
            sync_conn,
            "SELECT thema, kategorie FROM lesson_slots WHERE group_id = %s", GRUPPE
        ) == [("A", "unterricht")]

    async def test_vertretung_wandert_nicht_mit(self, sync_conn, anwenden):
        _slot(sync_conn, MO, thema="A", kategorie="vertretung")
        plan = plane_umhaengen(_alte(sync_conn), [NeuerTermin(MO2, 1, 1)])
        await anwenden(plan)

        assert _lese(
            sync_conn, "SELECT kategorie FROM lesson_slots WHERE group_id = %s", GRUPPE
        ) == [("unterricht",)]

    async def test_fixpunkt_behaelt_seine_kategorie(self, sync_conn, anwenden):
        """Er bewegt sich nicht — sonst würde aus der Klassenarbeit eine normale Stunde."""
        _slot(sync_conn, DI, thema="Klassenarbeit", kategorie="pruefung")
        plan = plane_umhaengen(_alte(sync_conn), [NeuerTermin(DI, 1, 1)])
        await anwenden(plan)

        assert _lese(
            sync_conn,
            "SELECT thema, kategorie, date FROM lesson_slots WHERE group_id = %s", GRUPPE
        ) == [("Klassenarbeit", "pruefung", DI)]


class TestUnparkEndpunkt:
    """Der Weg, den die Oberfläche geht (AP5).

    Plan-Operationen laufen sonst über das Chat-Werkzeug; für das Ziehen aus dem
    Parkplatz bekommt der eine Vorgang seinen eigenen Eingang — mit derselben Prüfung
    dahinter.
    """

    @pytest.fixture
    def eintrag(self, sync_conn):
        def _anlegen(thema="B"):
            eid = uuid.uuid4()
            sync_conn.rollback()
            with sync_conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO parked_lesson_content (id, group_id, halbjahr,"
                    " herkunft_datum, thema) VALUES (%s,%s,2,%s,%s)",
                    (str(eid), GRUPPE, DI, thema),
                )
            sync_conn.commit()
            return eid

        return _anlegen

    async def test_freie_stunde_nimmt_ihn_auf(
        self, sync_conn, eintrag, test_client, auth_headers
    ):
        ziel = _slot(sync_conn, MO2)
        eid = eintrag()

        antwort = await test_client.post(
            f"/planning/parkplatz/{eid}/unpark",
            json={"to_slot_id": str(ziel)},
            headers=auth_headers,
        )
        assert antwort.status_code == 200, antwort.text
        assert _lese(sync_conn, "SELECT thema FROM lesson_slots WHERE id = %s",
                     str(ziel)) == [("B",)]

    async def test_belegte_stunde_gibt_409(
        self, sync_conn, eintrag, test_client, auth_headers
    ):
        ziel = _slot(sync_conn, MO2, thema="schon da")
        eid = eintrag()

        antwort = await test_client.post(
            f"/planning/parkplatz/{eid}/unpark",
            json={"to_slot_id": str(ziel)},
            headers=auth_headers,
        )
        assert antwort.status_code == 409
        assert "belegt" in antwort.json()["detail"]
        assert _lese(sync_conn, "SELECT thema FROM lesson_slots WHERE id = %s",
                     str(ziel)) == [("schon da",)]

    async def test_fremde_lehrkraft_gibt_403(
        self, sync_conn, eintrag, test_client, auth_headers_teacher2
    ):
        ziel = _slot(sync_conn, MO2)
        eid = eintrag()
        antwort = await test_client.post(
            f"/planning/parkplatz/{eid}/unpark",
            json={"to_slot_id": str(ziel)},
            headers=auth_headers_teacher2,
        )
        assert antwort.status_code == 403

