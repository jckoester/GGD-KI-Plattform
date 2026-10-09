"""Eine neue Konversation bekommt nur eine Gruppe, in der die Person Mitglied ist.

Bis 0.14 übernahm `POST /chat` die `group_id` ungeprüft (nur `PATCH /conversations`
prüfte). Mit `/chat?group_id=<fremde Gruppe>` landete so der Block „Aktueller Unterricht"
einer fremden Gruppe im Prompt — Themen, Stundenziele, Klassenarbeit (`_planning_block`).

Der Test hält die Anfrage an `kontext_fuer_frage` an: Dort würde der Block geladen. Wer bis
dahin kommt, hat die Prüfung passiert; Netz und Modell bleiben dabei unberührt.
"""
from unittest.mock import AsyncMock, patch

import psycopg2
import pytest

from tests.integration.conftest import STUDENT_PSEUDO, TEACHER1_PSEUDO, TEACHER2_PSEUDO

EIGENE = 761   # teacher1 unterrichtet, student1 lernt
FREMDE = 762   # nur teacher2
KLASSE = 763   # teacher1 ist Mitglied, aber es ist eine Klasse, keine Unterrichtsgruppe
GRUPPEN = (EIGENE, FREMDE, KLASSE)

ABGEWIESEN = "Gruppe nicht gefunden oder keine Mitgliedschaft"


class _BisHierher(Exception):
    """Die Anfrage hat die Gruppenprüfung passiert."""


@pytest.fixture(scope="module")
def gruppen(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("INSERT INTO subjects (id, slug, name, sort_order) "
                    "VALUES (761, 'gruppenbezug', 'Gruppenbezug', 0) ON CONFLICT (id) DO NOTHING")
        for gid, typ in ((EIGENE, "teaching_group"), (FREMDE, "teaching_group"), (KLASSE, "school_class")):
            cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) "
                        "VALUES (%s, %s, %s, %s, 761) ON CONFLICT (id) DO NOTHING",
                        (gid, f"9g Bezug {gid}", f"bezug-{gid}", typ))
        for gid, pseudonym, rolle in ((EIGENE, TEACHER1_PSEUDO, "teacher"),
                                      (EIGENE, STUDENT_PSEUDO, "student"),
                                      (FREMDE, TEACHER2_PSEUDO, "teacher"),
                                      (KLASSE, TEACHER1_PSEUDO, "teacher")):
            cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                        "VALUES (%s, %s, %s, 'eigen') ON CONFLICT DO NOTHING", (gid, pseudonym, rolle))
    conn.commit()
    yield
    with conn.cursor() as cur:
        cur.execute("DELETE FROM conversations WHERE group_id = ANY(%s)", (list(GRUPPEN),))
        cur.execute("DELETE FROM groups WHERE id = ANY(%s)", (list(GRUPPEN),))
        cur.execute("DELETE FROM subjects WHERE id = 761")
    conn.commit()
    conn.close()


async def _neuer_chat(client, headers, group_id):
    """`POST /chat` mit Gruppe; gibt (Antwort oder None, Kontext-Attrappe) zurück."""
    kontext = AsyncMock(side_effect=_BisHierher)
    with patch("app.chat.router.kontext_fuer_frage", kontext):
        try:
            resp = await client.post("/chat", headers=headers, json={
                "messages": [{"role": "user", "content": "Was ist das aktuelle Thema?"}],
                "group_id": group_id,
            })
        except _BisHierher:
            return None, kontext
    return resp, kontext


@pytest.mark.asyncio
@pytest.mark.parametrize("gruppe", [FREMDE, KLASSE, 999_999])
async def test_ohne_mitgliedschaft_keine_konversation(test_client, auth_headers, gruppen, gruppe):
    """Fremde Gruppe, Klasse statt Unterrichtsgruppe, unbekannte Kennung — alles 404."""
    resp, kontext = await _neuer_chat(test_client, auth_headers, gruppe)
    assert resp is not None, "Die Anfrage kam bis zum Kontext — die Gruppe wurde nicht geprüft."
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == ABGEWIESEN
    kontext.assert_not_awaited()


@pytest.mark.asyncio
async def test_lehrkraft_der_gruppe_kommt_durch(test_client, auth_headers, gruppen):
    resp, kontext = await _neuer_chat(test_client, auth_headers, EIGENE)
    assert resp is None, resp.text
    kontext.assert_awaited_once()


@pytest.mark.asyncio
async def test_schuelerin_der_gruppe_kommt_durch(test_client, auth_headers_student, gruppen):
    """Schüler:innen chatten aus der Fachseite mit ihrer Gruppe — das bleibt."""
    resp, kontext = await _neuer_chat(test_client, auth_headers_student, EIGENE)
    assert resp is None, resp.text
    kontext.assert_awaited_once()
