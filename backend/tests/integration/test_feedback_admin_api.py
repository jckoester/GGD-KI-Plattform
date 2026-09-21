"""Die Sichtung der Rückmeldungen (ADR-020, AP3).

Der Schwerpunkt liegt auf dem, was ein Statuswechsel **mitnimmt**: Beim Abschluss
fallen die freiwillige Kontaktangabe immer und der angehängte Chat, sofern die
sichtende Person ihn nicht ausdrücklich behält. Das ist eine Löschzusage aus
ADR-011 §6.2 — sie gehört gegen die Datenbank geprüft, nicht gegen einen Mock.
"""
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest

from tests.integration.conftest import STUDENT_PSEUDO, TEACHER1_PSEUDO

PSEUDONYME = (STUDENT_PSEUDO, TEACHER1_PSEUDO)
MELDUNG = "Der Knopf zum Abschicken reagiert auf dem Handy nicht."
KONTAKT = "Jan, 10b"
ANHANG = {"conversation_id": "x", "messages": [{"role": "user", "content": "Hallo"}]}


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
            cur.execute("DELETE FROM feedback WHERE pseudonym = ANY(%s)", (list(PSEUDONYME),))
        sync_conn.commit()

    raeumen()
    yield
    raeumen()


def _meldung(sync_conn, *, pseudonym=STUDENT_PSEUDO, rolle="student", kategorie="bug",
             status="open", version="0.10.3", kontakt=None, anhang=None, vor=timedelta(0)):
    """Eine Zeile mit genau dem Zustand, den der Test braucht."""
    import json

    fid = uuid.uuid4()
    zeitpunkt = datetime.now(timezone.utc) - vor
    sync_conn.rollback()
    with sync_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO feedback (id, pseudonym, role, category, content, contact,"
            " app_version, status, conversation_snapshot, created_at, status_changed_at)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (str(fid), pseudonym, rolle, kategorie, MELDUNG, kontakt, version, status,
             json.dumps(anhang) if anhang else None, zeitpunkt,
             zeitpunkt if status != "open" else None),
        )
    sync_conn.commit()
    return str(fid)


def _zeile(conn, fid):
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, contact, conversation_snapshot, admin_reply,"
            " resolved_in_version, issue_ref, status_changed_at FROM feedback WHERE id = %s",
            (fid,),
        )
        return cur.fetchone()


# ── Zugang ──────────────────────────────────────────────────────────────────────

class TestZugang:
    async def test_schuelerin_kommt_nicht_an_die_liste(self, test_client, auth_headers_student):
        assert (await test_client.get("/admin/feedback",
                                      headers=auth_headers_student)).status_code == 403

    async def test_lehrkraft_ohne_admin_kommt_nicht_an_die_liste(
        self, test_client, auth_headers_teacher2
    ):
        assert (await test_client.get("/admin/feedback",
                                      headers=auth_headers_teacher2)).status_code == 403

    async def test_schuelerin_kann_nicht_patchen(
        self, test_client, sync_conn, auth_headers_student
    ):
        fid = _meldung(sync_conn)
        antwort = await test_client.patch(
            f"/admin/feedback/{fid}", json={"status": "done"}, headers=auth_headers_student
        )
        assert antwort.status_code == 403
        assert _zeile(sync_conn, fid)[0] == "open"


# ── Liste ───────────────────────────────────────────────────────────────────────

class TestListe:
    async def test_ohne_auswahl_nur_was_arbeit_macht(self, test_client, sync_conn, auth_headers):
        _meldung(sync_conn, status="open")
        _meldung(sync_conn, status="in_progress")
        _meldung(sync_conn, status="done")
        _meldung(sync_conn, status="spam")

        koerper = (await test_client.get("/admin/feedback", headers=auth_headers)).json()
        assert koerper["total"] == 2
        assert {e["status"] for e in koerper["items"]} == {"open", "in_progress"}

    async def test_status_laesst_sich_mehrfach_waehlen(self, test_client, sync_conn, auth_headers):
        _meldung(sync_conn, status="done")
        _meldung(sync_conn, status="declined")
        _meldung(sync_conn, status="open")

        koerper = (await test_client.get(
            "/admin/feedback?status=done&status=declined", headers=auth_headers
        )).json()
        assert koerper["total"] == 2

    async def test_unbekannter_status_wird_abgewiesen(self, test_client, auth_headers):
        antwort = await test_client.get("/admin/feedback?status=erledigt", headers=auth_headers)
        assert antwort.status_code == 422

    async def test_filter_nach_kategorie_rolle_version(self, test_client, sync_conn, auth_headers):
        _meldung(sync_conn, kategorie="bug", rolle="student", version="0.10.3")
        _meldung(sync_conn, kategorie="suggestion", rolle="student", version="0.10.3")
        _meldung(sync_conn, pseudonym=TEACHER1_PSEUDO, kategorie="bug", rolle="teacher",
                 version="0.10.2")

        async def zaehle(query):
            return (await test_client.get(f"/admin/feedback?{query}",
                                          headers=auth_headers)).json()["total"]

        assert await zaehle("category=bug") == 2
        assert await zaehle("role=teacher") == 1
        assert await zaehle("app_version=0.10.3") == 2
        assert await zaehle("category=bug&role=teacher") == 1

    async def test_neueste_zuerst(self, test_client, sync_conn, auth_headers):
        _meldung(sync_conn, kategorie="other", vor=timedelta(days=3))
        _meldung(sync_conn, kategorie="suggestion")
        items = (await test_client.get("/admin/feedback", headers=auth_headers)).json()["items"]
        assert [e["category"] for e in items] == ["suggestion", "other"]

    async def test_seitenweise(self, test_client, sync_conn, auth_headers):
        for _ in range(5):
            _meldung(sync_conn)
        koerper = (await test_client.get("/admin/feedback?limit=2&offset=2",
                                         headers=auth_headers)).json()
        assert koerper["total"] == 5 and len(koerper["items"]) == 2

    async def test_zaehler_haengen_nicht_am_status_filter(
        self, test_client, sync_conn, auth_headers
    ):
        """Sonst zeigte der Knopf „Erledigt" immer die Zahl, die gerade ausgewählt
        ist — und nie die, auf die man wechseln würde."""
        _meldung(sync_conn, status="open")
        _meldung(sync_conn, status="done")
        _meldung(sync_conn, status="done")

        koerper = (await test_client.get("/admin/feedback?status=open",
                                         headers=auth_headers)).json()
        assert koerper["total"] == 1
        assert koerper["counts"]["done"] == 2
        assert koerper["counts"]["open"] == 1
        assert koerper["counts"]["spam"] == 0, "Jeder Status hat einen Zähler, auch die leeren"

    async def test_zaehler_folgen_den_uebrigen_filtern(
        self, test_client, sync_conn, auth_headers
    ):
        _meldung(sync_conn, kategorie="bug", status="done")
        _meldung(sync_conn, kategorie="suggestion", status="done")
        koerper = (await test_client.get("/admin/feedback?category=bug",
                                         headers=auth_headers)).json()
        assert koerper["counts"]["done"] == 1

    async def test_der_anhang_steht_nicht_in_der_liste(
        self, test_client, sync_conn, auth_headers
    ):
        """Fünfzig Meldungen mit Chatverlauf wären ein Vielfaches an Inhalt, das
        niemand angefordert hat."""
        _meldung(sync_conn, anhang=ANHANG)
        eintrag = (await test_client.get("/admin/feedback",
                                         headers=auth_headers)).json()["items"][0]
        assert eintrag["has_snapshot"] is True
        assert "conversation_snapshot" not in eintrag


# ── Detail ──────────────────────────────────────────────────────────────────────

class TestDetail:
    async def test_detail_traegt_den_anhang(self, test_client, sync_conn, auth_headers):
        fid = _meldung(sync_conn, anhang=ANHANG, kontakt=KONTAKT)
        koerper = (await test_client.get(f"/admin/feedback/{fid}", headers=auth_headers)).json()
        assert koerper["conversation_snapshot"]["messages"][0]["content"] == "Hallo"
        assert koerper["contact"] == KONTAKT
        assert koerper["pseudonym"] == STUDENT_PSEUDO

    async def test_unbekannte_id_gibt_404(self, test_client, auth_headers):
        antwort = await test_client.get(f"/admin/feedback/{uuid.uuid4()}", headers=auth_headers)
        assert antwort.status_code == 404


# ── Statuswechsel ───────────────────────────────────────────────────────────────

class TestStatuswechsel:
    async def test_in_arbeit_nimmt_nichts_mit(self, test_client, sync_conn, auth_headers):
        """Erst der Abschluss räumt auf — wer bearbeitet, braucht den Kontakt noch."""
        fid = _meldung(sync_conn, kontakt=KONTAKT, anhang=ANHANG)
        antwort = await test_client.patch(
            f"/admin/feedback/{fid}", json={"status": "in_progress"}, headers=auth_headers
        )
        assert antwort.status_code == 200

        status, kontakt, anhang, *_rest, gewechselt = _zeile(sync_conn, fid)
        assert status == "in_progress"
        assert kontakt == KONTAKT
        assert anhang is not None
        assert gewechselt is not None

    async def test_abschluss_nullt_kontakt_und_anhang(self, test_client, sync_conn, auth_headers):
        """Die Löschzusage aus ADR-011 §6.2 — nach dem Abschluss gibt es nichts mehr
        nachzufragen, und der Anhang ist eine Kopie fremder Chatinhalte."""
        fid = _meldung(sync_conn, kontakt=KONTAKT, anhang=ANHANG)
        antwort = await test_client.patch(
            f"/admin/feedback/{fid}",
            json={"status": "done", "resolved_in_version": "0.10.4"},
            headers=auth_headers,
        )
        assert antwort.status_code == 200
        assert antwort.json()["has_snapshot"] is False

        status, kontakt, anhang, _antwort, version, _ref, _zeit = _zeile(sync_conn, fid)
        assert status == "done"
        assert kontakt is None
        assert anhang is None
        assert version == "0.10.4"

    async def test_anhang_laesst_sich_ausdruecklich_behalten(
        self, test_client, sync_conn, auth_headers
    ):
        fid = _meldung(sync_conn, kontakt=KONTAKT, anhang=ANHANG)
        await test_client.patch(
            f"/admin/feedback/{fid}", json={"status": "done", "keep_snapshot": True},
            headers=auth_headers,
        )
        _status, kontakt, anhang, *_ = _zeile(sync_conn, fid)
        assert anhang is not None, "Ausdrücklich behalten"
        assert kontakt is None, "Der Kontakt fällt trotzdem — dafür gibt es keine Option"

    async def test_behalten_ohne_abschluss_ist_kein_fehler(
        self, test_client, sync_conn, auth_headers
    ):
        """Die Oberfläche schickt die Auswahl mit, auch wenn der Status gleich bleibt."""
        fid = _meldung(sync_conn, anhang=ANHANG)
        antwort = await test_client.patch(
            f"/admin/feedback/{fid}", json={"issue_ref": "#142", "keep_snapshot": True},
            headers=auth_headers,
        )
        assert antwort.status_code == 200
        assert _zeile(sync_conn, fid)[5] == "#142"

    async def test_ablehnen_ohne_begruendung_wird_abgewiesen(
        self, test_client, sync_conn, auth_headers
    ):
        fid = _meldung(sync_conn)
        antwort = await test_client.patch(
            f"/admin/feedback/{fid}", json={"status": "declined"}, headers=auth_headers
        )
        assert antwort.status_code == 422
        assert _zeile(sync_conn, fid)[0] == "open", "Nichts halb geändert"

    async def test_ablehnen_mit_begruendung(self, test_client, sync_conn, auth_headers):
        fid = _meldung(sync_conn)
        antwort = await test_client.patch(
            f"/admin/feedback/{fid}",
            json={"status": "declined", "admin_reply": "Funktioniert wie vorgesehen."},
            headers=auth_headers,
        )
        assert antwort.status_code == 200
        assert _zeile(sync_conn, fid)[3] == "Funktioniert wie vorgesehen."

    async def test_leere_begruendung_zaehlt_nicht(self, test_client, sync_conn, auth_headers):
        fid = _meldung(sync_conn)
        antwort = await test_client.patch(
            f"/admin/feedback/{fid}", json={"status": "declined", "admin_reply": "   "},
            headers=auth_headers,
        )
        assert antwort.status_code == 422

    async def test_vorhandene_begruendung_genuegt_beim_nachbearbeiten(
        self, test_client, sync_conn, auth_headers
    ):
        """Geprüft wird der Endzustand, nicht die Eingabe: Wer nur die Issue-Referenz
        nachträgt, muss die Begründung nicht noch einmal tippen."""
        fid = _meldung(sync_conn)
        await test_client.patch(
            f"/admin/feedback/{fid}", json={"status": "declined", "admin_reply": "Kein Fehler."},
            headers=auth_headers,
        )
        antwort = await test_client.patch(
            f"/admin/feedback/{fid}", json={"issue_ref": "#7"}, headers=auth_headers
        )
        assert antwort.status_code == 200

    async def test_unvorgesehener_wechsel_gibt_409(self, test_client, sync_conn, auth_headers):
        """`done → declined` liefe am Wiedereröffnen vorbei und schriebe den
        Zeitstempel neu, obwohl der Anhang längst gefallen ist."""
        fid = _meldung(sync_conn, status="done")
        antwort = await test_client.patch(
            f"/admin/feedback/{fid}",
            json={"status": "declined", "admin_reply": "Doch nicht."},
            headers=auth_headers,
        )
        assert antwort.status_code == 409
        assert _zeile(sync_conn, fid)[0] == "done"

    async def test_wiedereroeffnen_geht(self, test_client, sync_conn, auth_headers):
        fid = _meldung(sync_conn, status="done")
        antwort = await test_client.patch(
            f"/admin/feedback/{fid}", json={"status": "open"}, headers=auth_headers
        )
        assert antwort.status_code == 200
        assert antwort.json()["has_snapshot"] is False, "Der Anhang ist beim Abschluss gefallen"

    async def test_unbekannter_status_wird_abgewiesen(self, test_client, sync_conn, auth_headers):
        fid = _meldung(sync_conn)
        antwort = await test_client.patch(
            f"/admin/feedback/{fid}", json={"status": "erledigt"}, headers=auth_headers
        )
        assert antwort.status_code == 422

    async def test_meldung_die_es_nicht_gibt(self, test_client, auth_headers):
        antwort = await test_client.patch(
            f"/admin/feedback/{uuid.uuid4()}", json={"status": "done"}, headers=auth_headers
        )
        assert antwort.status_code == 404
