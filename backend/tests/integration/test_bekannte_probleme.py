"""Bekannte Probleme (0.31, Päckchen T, Plan Schritt 2). Erfordert TEST_DATABASE_URL.

Öffentlich ist nur der Titel, den die Sichtung schreibt — nie der Text der Meldung. Das ist
die Zusage, die hier zuerst geprüft wird.
"""
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest

from tests.integration.conftest import STUDENT_PSEUDO, TEACHER1_PSEUDO

PSEUDONYME = (STUDENT_PSEUDO, TEACHER1_PSEUDO)
MELDUNG = "Im PDF-Export rutschen die Formeln aus der Tabelle, Klasse 10b, Herr Muster."


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


def _meldung(sync_conn, *, status="open", titel=None, zielgruppe=None, vor=timedelta(0),
             version=None):
    fid = uuid.uuid4()
    zeitpunkt = datetime.now(timezone.utc) - vor
    sync_conn.rollback()
    with sync_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO feedback (id, pseudonym, role, category, content, app_version, status,"
            " created_at, status_changed_at, public_title, public_audience, resolved_in_version)"
            " VALUES (%s,%s,'student','bug',%s,'0.30.0',%s,%s,%s,%s,%s,%s)",
            (str(fid), STUDENT_PSEUDO, MELDUNG, status, zeitpunkt,
             zeitpunkt if status != "open" else None, titel, zielgruppe, version),
        )
    sync_conn.commit()
    return str(fid)


def _oeffentlich(sync_conn, fid):
    sync_conn.rollback()
    with sync_conn.cursor() as cur:
        cur.execute("SELECT public_title, public_audience FROM feedback WHERE id = %s", (fid,))
        return cur.fetchone()


async def _liste(client, headers):
    antwort = await client.get("/feedback/public", headers=headers)
    assert antwort.status_code == 200, antwort.text
    return antwort.json()


# ── Öffentliche Liste ───────────────────────────────────────────────────────────

class TestListe:
    async def test_zeigt_nur_den_titel_nie_die_meldung(
        self, test_client, sync_conn, auth_headers_student
    ):
        _meldung(sync_conn, titel="Formeln im PDF verrutschen", zielgruppe="all")
        liste = await _liste(test_client, auth_headers_student)
        assert [e["title"] for e in liste] == ["Formeln im PDF verrutschen"]
        assert set(liste[0]) == {"id", "title", "status", "resolved_in_version", "seit"}
        assert "Muster" not in str(liste)

    async def test_zielgruppe_lehrkraefte(
        self, test_client, sync_conn, auth_headers_student, auth_headers_teacher2, auth_headers
    ):
        _meldung(sync_conn, titel="Für alle", zielgruppe="all")
        _meldung(sync_conn, titel="Nur Lehrkräfte", zielgruppe="teacher")
        _meldung(sync_conn, titel="Nicht öffentlich")
        assert [e["title"] for e in await _liste(test_client, auth_headers_student)] == ["Für alle"]
        for kopf in (auth_headers_teacher2, auth_headers):  # Lehrkraft, Admin
            titel = {e["title"] for e in await _liste(test_client, kopf)}
            assert titel == {"Für alle", "Nur Lehrkräfte"}

    async def test_behobenes_bleibt_dreissig_tage(
        self, test_client, sync_conn, auth_headers_student
    ):
        _meldung(sync_conn, status="done", titel="Frisch behoben", zielgruppe="all",
                 vor=timedelta(days=3), version="0.31.1")
        _meldung(sync_conn, status="done", titel="Lange her", zielgruppe="all",
                 vor=timedelta(days=31))
        liste = await _liste(test_client, auth_headers_student)
        assert [(e["title"], e["status"], e["resolved_in_version"]) for e in liste] == [
            ("Frisch behoben", "done", "0.31.1")]

    async def test_offenes_vor_behobenem(self, test_client, sync_conn, auth_headers_student):
        _meldung(sync_conn, status="done", titel="Behoben", zielgruppe="all")
        _meldung(sync_conn, status="open", titel="Alt offen", zielgruppe="all",
                 vor=timedelta(days=5))
        _meldung(sync_conn, status="in_progress", titel="Neu in Arbeit", zielgruppe="all")
        titel = [e["title"] for e in await _liste(test_client, auth_headers_student)]
        assert titel == ["Neu in Arbeit", "Alt offen", "Behoben"]

    async def test_braucht_anmeldung(self, test_client):
        assert (await test_client.get("/feedback/public")).status_code == 401


# ── Sichtung: zeigen und zurücknehmen ───────────────────────────────────────────

class TestSichtung:
    async def test_zeigen_und_zuruecknehmen(self, test_client, sync_conn, auth_headers):
        fid = _meldung(sync_conn)
        antwort = await test_client.patch(f"/admin/feedback/{fid}", headers=auth_headers, json={
            "public_title": "  Formeln im PDF verrutschen ", "public_audience": "teacher"})
        assert antwort.status_code == 200, antwort.text
        assert antwort.json()["public_audience"] == "teacher"
        assert _oeffentlich(sync_conn, fid) == ("Formeln im PDF verrutschen", "teacher")

        antwort = await test_client.patch(f"/admin/feedback/{fid}", headers=auth_headers,
                                          json={"public_audience": "none"})
        assert antwort.status_code == 200
        assert _oeffentlich(sync_conn, fid) == ("Formeln im PDF verrutschen", None)

    async def test_ohne_titel_abgewiesen(self, test_client, sync_conn, auth_headers):
        fid = _meldung(sync_conn)
        for titel in (None, "   "):
            antwort = await test_client.patch(f"/admin/feedback/{fid}", headers=auth_headers,
                                              json={"public_title": titel, "public_audience": "all"})
            assert antwort.status_code == 422
            assert "Titel" in antwort.json()["detail"]
        assert _oeffentlich(sync_conn, fid) == (None, None)

    async def test_titel_leeren_waehrend_oeffentlich_abgewiesen(
        self, test_client, sync_conn, auth_headers
    ):
        fid = _meldung(sync_conn, titel="Bekannt", zielgruppe="all")
        antwort = await test_client.patch(f"/admin/feedback/{fid}", headers=auth_headers,
                                          json={"public_title": ""})
        assert antwort.status_code == 422

    async def test_ablehnen_nimmt_aus_der_liste(self, test_client, sync_conn, auth_headers):
        fid = _meldung(sync_conn, titel="Bekannt", zielgruppe="all")
        antwort = await test_client.patch(f"/admin/feedback/{fid}", headers=auth_headers, json={
            "status": "declined", "admin_reply": "Ist so gewollt."})
        assert antwort.status_code == 200, antwort.text
        assert _oeffentlich(sync_conn, fid) == ("Bekannt", None)

    async def test_abgelehnt_und_oeffentlich_zugleich_abgewiesen(
        self, test_client, sync_conn, auth_headers
    ):
        fid = _meldung(sync_conn)
        antwort = await test_client.patch(f"/admin/feedback/{fid}", headers=auth_headers, json={
            "status": "spam", "public_title": "X", "public_audience": "all"})
        assert antwort.status_code == 422
        assert _oeffentlich(sync_conn, fid) == (None, None)

    async def test_unbekannte_zielgruppe(self, test_client, sync_conn, auth_headers):
        fid = _meldung(sync_conn)
        antwort = await test_client.patch(f"/admin/feedback/{fid}", headers=auth_headers, json={
            "public_title": "X", "public_audience": "eltern"})
        assert antwort.status_code == 422

    async def test_audit_haelt_den_wechsel_fest(self, test_client, sync_conn, auth_headers):
        fid = _meldung(sync_conn)
        await test_client.patch(f"/admin/feedback/{fid}", headers=auth_headers, json={
            "public_title": "Bekannt", "public_audience": "all"})
        sync_conn.rollback()
        with sync_conn.cursor() as cur:
            cur.execute("SELECT category, payload FROM audit_log WHERE event_type ="
                        " 'feedback_public_changed' AND target_id = %s", (fid,))
            zeilen = cur.fetchall()
        assert zeilen == [("admin", {"von": None, "nach": "all"})]

    async def test_lehrkraft_ohne_admin_darf_nicht(
        self, test_client, sync_conn, auth_headers_teacher2
    ):
        fid = _meldung(sync_conn)
        antwort = await test_client.patch(f"/admin/feedback/{fid}", headers=auth_headers_teacher2,
                                          json={"public_title": "X", "public_audience": "all"})
        assert antwort.status_code == 403


async def test_vorschau_zeigt_die_schuelersicht(test_client, sync_conn, jwt_service):
    """Lehrkraft in der Vorschau (0.29): Maßgeblich sind die simulierten Rollen im Token."""
    import time

    from app.auth.vorschau import Vorschau

    _meldung(sync_conn, titel="Für alle", zielgruppe="all")
    _meldung(sync_conn, titel="Nur Lehrkräfte", zielgruppe="teacher")
    jetzt = int(time.time())
    token, _ = jwt_service.issue(
        pseudonym=TEACHER1_PSEUDO, roles=["student"], grade="9",
        preview=Vorschau(echte_rollen=["teacher"], beginn=jetzt, sitzung_ablauf=jetzt + 3600),
        exp=jetzt + 3600,
    )
    liste = await _liste(test_client, {"Cookie": f"session={token}"})
    assert [e["title"] for e in liste] == ["Für alle"]
