"""Die drei Nutzer-Endpunkte des Feedback-Kanals (ADR-020, AP2).

Warum gegen die Datenbank und nicht mit Mocks: Sperre, Tageslimit, Eigentumsprüfung und
Snapshot sind Aussagen über SQL — welche Zeile welches `WHERE` trifft. Ein Mock bewiese
davon nichts.

⚠️ **Zwei gemeinsame Zustände, die zwischen Tests durchschlagen würden**, beide in
`autouse`-Fixturen abgeräumt: die Drossel (prozess-lokaler Zähler) und die Meldungen der
Testpseudonyme selbst — ohne sie summierte sich das Tageslimit über die Tests hinweg,
und wer zuletzt liefe, bekäme 429 ohne Zutun.
"""
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest

from tests.integration.conftest import STUDENT_PSEUDO, TEACHER1_PSEUDO

PSEUDONYME = (STUDENT_PSEUDO, TEACHER1_PSEUDO)

MELDUNG = "Der Knopf zum Abschicken reagiert auf dem Handy nicht."


def _rumpf(**abweichend):
    basis = {"category": "bug", "content": MELDUNG, "app_version": "0.10.3"}
    basis.update(abweichend)
    return basis


@pytest.fixture(scope="module")
def sync_conn(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def leerer_zaehler():
    """Die Drossel ist prozess-lokal und überlebt sonst den Test."""
    from app.ratelimit import store

    store.reset()
    yield
    store.reset()


@pytest.fixture(autouse=True)
def leere_tabelle(sync_conn):
    """Kein Test erbt die Meldungen des vorigen — sonst wandert das Tageslimit mit."""
    def raeumen():
        sync_conn.rollback()
        with sync_conn.cursor() as cur:
            cur.execute("DELETE FROM feedback WHERE pseudonym = ANY(%s)", (list(PSEUDONYME),))
        sync_conn.commit()

    raeumen()
    yield
    raeumen()


def _meldungen(cur, pseudonym, anzahl, *, status="open", vor: timedelta = timedelta(0)):
    """Fertige Zeilen in der Datenbank — schneller als `anzahl` echte Anfragen, und
    unabhängig von der Stundendrossel, die hier nicht geprüft wird."""
    zeitpunkt = datetime.now(timezone.utc) - vor
    for _ in range(anzahl):
        cur.execute(
            "INSERT INTO feedback (id, pseudonym, role, category, content, app_version,"
            " status, created_at, status_changed_at)"
            " VALUES (%s,%s,'student','other',%s,'0.10.3',%s,%s,%s)",
            (str(uuid.uuid4()), pseudonym, MELDUNG, status, zeitpunkt,
             zeitpunkt if status != "open" else None),
        )


def _zeile(conn, pseudonym):
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT role, category, content, contact, route, app_version, status,"
            " conversation_snapshot FROM feedback WHERE pseudonym = %s", (pseudonym,)
        )
        return cur.fetchone()


def _konversation(cur, pseudonym, *, nachrichten=0, titel="Bruchrechnen"):
    kid = uuid.uuid4()
    cur.execute(
        "INSERT INTO conversations (id, pseudonym, model_used, title)"
        " VALUES (%s,%s,'chat-standard',%s)",
        (str(kid), pseudonym, titel),
    )
    start = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)
    for i in range(nachrichten):
        cur.execute(
            "INSERT INTO messages (id, conversation_id, role, content, created_at)"
            " VALUES (%s,%s,%s,%s,%s)",
            (str(uuid.uuid4()), str(kid), "user" if i % 2 == 0 else "assistant",
             f"Nachricht {i}", start + timedelta(minutes=i)),
        )
    return kid


# ── Anlegen ─────────────────────────────────────────────────────────────────────

class TestAnlegen:
    async def test_meldung_wird_gespeichert(self, test_client, sync_conn, auth_headers_student):
        antwort = await test_client.post(
            "/feedback", json=_rumpf(contact="Jan, 10b", route="/chat?id=7"),
            headers=auth_headers_student,
        )
        assert antwort.status_code == 201, antwort.text
        koerper = antwort.json()
        assert koerper["status"] == "open"
        assert koerper["has_snapshot"] is False

        rolle, kategorie, inhalt, kontakt, route, version, status, anhang = _zeile(
            sync_conn, STUDENT_PSEUDO
        )
        assert (rolle, kategorie, status) == ("student", "bug", "open")
        assert inhalt == MELDUNG
        assert kontakt == "Jan, 10b"
        assert route == "/chat", "Die Query gehört nicht in die Meldung"
        assert version == "0.10.3"
        assert anhang is None

    async def test_rolle_kommt_aus_dem_jwt(self, test_client, sync_conn, auth_headers):
        """`auth_headers` ist Lehrkraft **und** Admin — festgehalten wird die
        Primärrolle, nicht die additive."""
        await test_client.post("/feedback", json=_rumpf(), headers=auth_headers)
        assert _zeile(sync_conn, TEACHER1_PSEUDO)[0] == "teacher"

    async def test_zu_kurze_meldung_wird_abgewiesen(self, test_client, auth_headers_student):
        antwort = await test_client.post(
            "/feedback", json=_rumpf(content="kaputt"), headers=auth_headers_student
        )
        assert antwort.status_code == 422

    async def test_ohne_anmeldung_401(self, test_client):
        assert (await test_client.post("/feedback", json=_rumpf())).status_code == 401


# ── Chat-Anhang ─────────────────────────────────────────────────────────────────

class TestAnhang:
    async def test_eigener_chat_haengt_als_kopie_an(
        self, test_client, sync_conn, auth_headers_student
    ):
        with sync_conn.cursor() as cur:
            kid = _konversation(cur, STUDENT_PSEUDO, nachrichten=3)
        sync_conn.commit()

        antwort = await test_client.post(
            "/feedback", json=_rumpf(attach_conversation_id=str(kid)),
            headers=auth_headers_student,
        )
        assert antwort.status_code == 201, antwort.text
        assert antwort.json()["has_snapshot"] is True

        anhang = _zeile(sync_conn, STUDENT_PSEUDO)[7]
        assert anhang["title"] == "Bruchrechnen"
        assert anhang["model_used"] == "chat-standard"
        assert [n["content"] for n in anhang["messages"]] == [
            "Nachricht 0", "Nachricht 1", "Nachricht 2"
        ]

    async def test_der_anhang_traegt_keine_kosten(
        self, test_client, sync_conn, auth_headers_student
    ):
        with sync_conn.cursor() as cur:
            kid = _konversation(cur, STUDENT_PSEUDO, nachrichten=1)
        sync_conn.commit()
        await test_client.post(
            "/feedback", json=_rumpf(attach_conversation_id=str(kid)),
            headers=auth_headers_student,
        )
        anhang = _zeile(sync_conn, STUDENT_PSEUDO)[7]
        assert set(anhang["messages"][0]) == {"role", "content", "model", "created_at"}

    async def test_lange_chats_werden_auf_die_letzten_50_gekuerzt(
        self, test_client, sync_conn, auth_headers_student
    ):
        with sync_conn.cursor() as cur:
            kid = _konversation(cur, STUDENT_PSEUDO, nachrichten=60)
        sync_conn.commit()
        await test_client.post(
            "/feedback", json=_rumpf(attach_conversation_id=str(kid)),
            headers=auth_headers_student,
        )
        nachrichten = _zeile(sync_conn, STUDENT_PSEUDO)[7]["messages"]
        assert len(nachrichten) == 50
        assert nachrichten[0]["content"] == "Nachricht 10", "Die letzten 50, nicht die ersten"
        assert nachrichten[-1]["content"] == "Nachricht 59"

    async def test_fremder_chat_gibt_404_und_legt_nichts_an(
        self, test_client, sync_conn, auth_headers_student
    ):
        """404 statt 403: Ein 403 verriete, dass es die fremde Konversation gibt."""
        with sync_conn.cursor() as cur:
            kid = _konversation(cur, TEACHER1_PSEUDO, nachrichten=2)
        sync_conn.commit()

        antwort = await test_client.post(
            "/feedback", json=_rumpf(attach_conversation_id=str(kid)),
            headers=auth_headers_student,
        )
        assert antwort.status_code == 404
        assert _zeile(sync_conn, STUDENT_PSEUDO) is None


# ── Meine Meldungen ─────────────────────────────────────────────────────────────

class TestMeineMeldungen:
    async def test_neueste_zuerst_und_nur_eigene(
        self, test_client, sync_conn, auth_headers_student
    ):
        with sync_conn.cursor() as cur:
            _meldungen(cur, STUDENT_PSEUDO, 1, vor=timedelta(days=2))
            _meldungen(cur, TEACHER1_PSEUDO, 1)
        sync_conn.commit()
        await test_client.post("/feedback", json=_rumpf(content="Die neuere Meldung hier."),
                               headers=auth_headers_student)

        liste = (await test_client.get("/feedback/mine", headers=auth_headers_student)).json()
        assert len(liste) == 2
        assert liste[0]["content"] == "Die neuere Meldung hier."

    async def test_spam_erscheint_als_abgelehnt_ohne_begruendung(
        self, test_client, sync_conn, auth_headers_student
    ):
        """Der Kanal ist eine Einbahnstraße — eine Begründung lüde zum Widerspruch ein."""
        sync_conn.rollback()
        with sync_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO feedback (id, pseudonym, role, category, content, app_version,"
                " status, admin_reply, status_changed_at)"
                " VALUES (%s,%s,'student','other',%s,'0.10.3','spam','Unsinn',now())",
                (str(uuid.uuid4()), STUDENT_PSEUDO, MELDUNG),
            )
        sync_conn.commit()

        eintrag = (await test_client.get("/feedback/mine", headers=auth_headers_student)).json()[0]
        assert eintrag["status"] == "declined"
        assert eintrag["admin_reply"] is None

    async def test_interne_issue_referenz_bleibt_drin(
        self, test_client, sync_conn, auth_headers_student
    ):
        """`issue_ref` ist eine Arbeitsnotiz der Sichtung, kein Teil der Antwort."""
        sync_conn.rollback()
        with sync_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO feedback (id, pseudonym, role, category, content, app_version,"
                " issue_ref) VALUES (%s,%s,'student','bug',%s,'0.10.3','#142')",
                (str(uuid.uuid4()), STUDENT_PSEUDO, MELDUNG),
            )
        sync_conn.commit()

        eintrag = (await test_client.get("/feedback/mine", headers=auth_headers_student)).json()[0]
        assert "issue_ref" not in eintrag
        assert "conversation_snapshot" not in eintrag


# ── Zurückziehen ────────────────────────────────────────────────────────────────

class TestZurueckziehen:
    async def test_offene_meldung_verschwindet(
        self, test_client, sync_conn, auth_headers_student
    ):
        angelegt = await test_client.post("/feedback", json=_rumpf(),
                                          headers=auth_headers_student)
        fid = angelegt.json()["id"]

        antwort = await test_client.delete(f"/feedback/{fid}", headers=auth_headers_student)
        assert antwort.status_code == 200
        assert _zeile(sync_conn, STUDENT_PSEUDO) is None

    async def test_fremde_meldung_gibt_404(
        self, test_client, sync_conn, auth_headers_student, auth_headers
    ):
        angelegt = await test_client.post("/feedback", json=_rumpf(), headers=auth_headers)
        fid = angelegt.json()["id"]

        antwort = await test_client.delete(f"/feedback/{fid}", headers=auth_headers_student)
        assert antwort.status_code == 404
        assert _zeile(sync_conn, TEACHER1_PSEUDO) is not None

    async def test_in_bearbeitung_gibt_409(
        self, test_client, sync_conn, auth_headers_student
    ):
        """Was die Sichtung schon angefasst hat, verschwindet ihr nicht unter den Händen."""
        angelegt = await test_client.post("/feedback", json=_rumpf(),
                                          headers=auth_headers_student)
        fid = angelegt.json()["id"]
        sync_conn.rollback()
        with sync_conn.cursor() as cur:
            cur.execute("UPDATE feedback SET status = 'in_progress' WHERE id = %s", (fid,))
        sync_conn.commit()

        antwort = await test_client.delete(f"/feedback/{fid}", headers=auth_headers_student)
        assert antwort.status_code == 409
        assert _zeile(sync_conn, STUDENT_PSEUDO) is not None


# ── Missbrauchsschutz ───────────────────────────────────────────────────────────

class TestTageslimit:
    async def test_neunzehn_vorher_ist_noch_frei(
        self, test_client, sync_conn, auth_headers_student
    ):
        with sync_conn.cursor() as cur:
            _meldungen(cur, STUDENT_PSEUDO, 19, vor=timedelta(hours=2))
        sync_conn.commit()
        antwort = await test_client.post("/feedback", json=_rumpf(),
                                         headers=auth_headers_student)
        assert antwort.status_code == 201

    async def test_zwanzig_vorher_gibt_429(
        self, test_client, sync_conn, auth_headers_student
    ):
        with sync_conn.cursor() as cur:
            _meldungen(cur, STUDENT_PSEUDO, 20, vor=timedelta(hours=2))
        sync_conn.commit()
        antwort = await test_client.post("/feedback", json=_rumpf(),
                                         headers=auth_headers_student)
        assert antwort.status_code == 429
        # Bis die älteste aus dem Fenster fällt, nicht pauschal 24 Stunden.
        assert 0 < int(antwort.headers["Retry-After"]) <= 22 * 3600

    async def test_aeltere_meldungen_zaehlen_nicht_mehr(
        self, test_client, sync_conn, auth_headers_student
    ):
        with sync_conn.cursor() as cur:
            _meldungen(cur, STUDENT_PSEUDO, 25, vor=timedelta(hours=25))
        sync_conn.commit()
        antwort = await test_client.post("/feedback", json=_rumpf(),
                                         headers=auth_headers_student)
        assert antwort.status_code == 201


class TestSpamSperre:
    """Drei `spam` in 30 Tagen sperren 14 Tage — gerechnet ab dem **jüngsten**."""

    async def test_zwei_sperren_nicht(self, test_client, sync_conn, auth_headers_student):
        with sync_conn.cursor() as cur:
            _meldungen(cur, STUDENT_PSEUDO, 2, status="spam", vor=timedelta(days=1))
        sync_conn.commit()
        assert (await test_client.post("/feedback", json=_rumpf(),
                                       headers=auth_headers_student)).status_code == 201

    async def test_drei_frische_sperren(self, test_client, sync_conn, auth_headers_student):
        with sync_conn.cursor() as cur:
            _meldungen(cur, STUDENT_PSEUDO, 3, status="spam", vor=timedelta(days=13))
        sync_conn.commit()
        antwort = await test_client.post("/feedback", json=_rumpf(),
                                         headers=auth_headers_student)
        assert antwort.status_code == 403
        assert "gesperrt bis" in antwort.json()["detail"]

    async def test_nach_vierzehn_tagen_wieder_frei(
        self, test_client, sync_conn, auth_headers_student
    ):
        with sync_conn.cursor() as cur:
            _meldungen(cur, STUDENT_PSEUDO, 3, status="spam", vor=timedelta(days=15))
        sync_conn.commit()
        assert (await test_client.post("/feedback", json=_rumpf(),
                                       headers=auth_headers_student)).status_code == 201

    async def test_der_juengste_bestimmt_das_ende(
        self, test_client, sync_conn, auth_headers_student
    ):
        """Zwei alte und ein frischer Eintrag: Die Sperre läuft ab dem frischen.

        Mit `min(...) + 14 Tage` — dem ersten Verstoß — wäre sie hier längst abgelaufen.
        """
        with sync_conn.cursor() as cur:
            _meldungen(cur, STUDENT_PSEUDO, 2, status="spam", vor=timedelta(days=28))
            _meldungen(cur, STUDENT_PSEUDO, 1, status="spam", vor=timedelta(days=1))
        sync_conn.commit()
        assert (await test_client.post("/feedback", json=_rumpf(),
                                       headers=auth_headers_student)).status_code == 403

    async def test_aus_dem_30_tage_fenster_gefallen(
        self, test_client, sync_conn, auth_headers_student
    ):
        with sync_conn.cursor() as cur:
            _meldungen(cur, STUDENT_PSEUDO, 2, status="spam", vor=timedelta(days=31))
            _meldungen(cur, STUDENT_PSEUDO, 1, status="spam", vor=timedelta(days=1))
        sync_conn.commit()
        assert (await test_client.post("/feedback", json=_rumpf(),
                                       headers=auth_headers_student)).status_code == 201


class TestStundendrossel:
    async def test_die_sechste_meldung_in_einer_stunde_wird_gebremst(
        self, test_client, auth_headers_student
    ):
        stati = [
            (await test_client.post("/feedback", json=_rumpf(), headers=auth_headers_student)).status_code
            for _ in range(6)
        ]
        assert stati == [201] * 5 + [429]

    async def test_lesen_bleibt_frei(self, test_client, auth_headers_student):
        """Der Eimer zählt je Pseudonym, nicht je Endpunkt — an `GET /mine` gehängt,
        wäre man nach fünf Aufrufen aus der eigenen Meldungsliste ausgesperrt."""
        for _ in range(6):
            await test_client.post("/feedback", json=_rumpf(), headers=auth_headers_student)
        for _ in range(8):
            assert (await test_client.get("/feedback/mine",
                                          headers=auth_headers_student)).status_code == 200
