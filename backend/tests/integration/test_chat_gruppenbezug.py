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
DOPPELT_A, DOPPELT_B = 764, 765   # student1 in zwei Gruppen desselben Fachs (762)
GRUPPEN = (EIGENE, FREMDE, KLASSE, DOPPELT_A, DOPPELT_B)

ABGEWIESEN = "Gruppe nicht gefunden oder keine Mitgliedschaft"


class _BisHierher(Exception):
    """Die Anfrage hat die Gruppenprüfung passiert."""


@pytest.fixture(scope="module")
def gruppen(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("INSERT INTO subjects (id, slug, name, sort_order) "
                    "VALUES (761, 'gruppenbezug', 'Gruppenbezug', 0) ON CONFLICT (id) DO NOTHING")
        cur.execute("INSERT INTO subjects (id, slug, name, sort_order) "
                    "VALUES (762, 'gruppenbezug-zwei', 'Gruppenbezug zwei', 0), "
                    "(763, 'gruppenbezug-leer', 'Gruppenbezug leer', 0) ON CONFLICT (id) DO NOTHING")
        for gid, typ, fach in ((EIGENE, "teaching_group", 761), (FREMDE, "teaching_group", 761),
                               (KLASSE, "school_class", 761), (DOPPELT_A, "teaching_group", 762),
                               (DOPPELT_B, "teaching_group", 762)):
            cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) "
                        "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                        (gid, f"9g Bezug {gid}", f"bezug-{gid}", typ, fach))
        for gid, pseudonym, rolle in ((EIGENE, TEACHER1_PSEUDO, "teacher"),
                                      (EIGENE, STUDENT_PSEUDO, "student"),
                                      (FREMDE, TEACHER2_PSEUDO, "teacher"),
                                      (KLASSE, TEACHER1_PSEUDO, "teacher"),
                                      (DOPPELT_A, STUDENT_PSEUDO, "student"),
                                      (DOPPELT_B, STUDENT_PSEUDO, "student")):
            cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                        "VALUES (%s, %s, %s, 'eigen') ON CONFLICT DO NOTHING", (gid, pseudonym, rolle))
    conn.commit()
    yield
    with conn.cursor() as cur:
        cur.execute("DELETE FROM conversations WHERE group_id = ANY(%s)", (list(GRUPPEN),))
        cur.execute("DELETE FROM groups WHERE id = ANY(%s)", (list(GRUPPEN),))
        cur.execute("DELETE FROM subjects WHERE id IN (761, 762, 763)")
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


# ── 0.20 (Päckchen AC, F1): Gruppe aus dem Fach ─────────────────────────────


async def _gruppe_der_neuen_konversation(client, headers, subject_id):
    """`POST /chat` nur mit Fach; gibt die `group_id` zurück, mit der die Konversation beim
    Kontext ankommt (`kontext_fuer_frage` liest sie dort aus der Zeile)."""
    from app.db.models import Conversation

    gesehen = {}

    async def anhalten(*, chat_id, db, **_):
        gesehen["gruppe"] = (await db.get(Conversation, chat_id)).group_id
        raise _BisHierher

    with patch("app.chat.router.kontext_fuer_frage", AsyncMock(side_effect=anhalten)):
        with pytest.raises(_BisHierher):
            await client.post("/chat", headers=headers, json={
                "messages": [{"role": "user", "content": "Was ist das aktuelle Thema?"}],
                "subject_id": subject_id,
            })
    return gesehen["gruppe"]


@pytest.mark.asyncio
async def test_schuelerin_mit_einer_gruppe_im_fach_bekommt_sie(test_client, auth_headers_student, gruppen):
    assert await _gruppe_der_neuen_konversation(test_client, auth_headers_student, 761) == EIGENE


@pytest.mark.asyncio
async def test_schuelerin_mit_zwei_gruppen_im_fach_bleibt_beim_fach(test_client, auth_headers_student, gruppen):
    """Nicht raten — vgl. `schuelerWeiche`."""
    assert await _gruppe_der_neuen_konversation(test_client, auth_headers_student, 762) is None


@pytest.mark.asyncio
async def test_schuelerin_ohne_gruppe_im_fach_bleibt_beim_fach(test_client, auth_headers_student, gruppen):
    assert await _gruppe_der_neuen_konversation(test_client, auth_headers_student, 763) is None


@pytest.mark.asyncio
async def test_lehrkraft_bleibt_auf_der_fach_ebene(test_client, auth_headers, gruppen):
    """teacher1 hat im Fach genau eine Unterrichtsgruppe (die Klasse zählt nicht) — und bleibt
    trotzdem beim Fach: Das ist ihre persönliche Fach-Ebene (Jan, 20.10.2026)."""
    assert await _gruppe_der_neuen_konversation(test_client, auth_headers, 761) is None
