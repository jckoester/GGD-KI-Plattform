"""Gepufferte Bausteine liegen schon der ersten Antwort vor (0.41, Fix nach Schritt 10).

Bis dahin heftete der Chat sie erst an, nachdem der Server den Kontext der ersten Antwort gebaut
hatte. Jetzt kommen sie mit der ersten Nachricht (`ChatRequest.kontext_node_ids`) und werden
**vor** `kontext_fuer_frage` angeheftet — mit denselben Regeln wie `POST …/nodes`.
"""
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import psycopg2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.jwt import JwtPayload
from app.context.router import knoten_beim_anlegen_anheften
from app.context.service import kontext_fuer_frage
from tests.integration.conftest import STUDENT_PSEUDO, TEACHER1_PSEUDO, TEACHER2_PSEUDO

pytestmark = pytest.mark.asyncio

ICH = TEACHER2_PSEUDO
GRUPPE = 9641


@pytest.fixture
def conn(db_url, run_migrations):
    c = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))

    def aufraeumen():
        with c.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE title = 'FIX1 Chat'")
            cur.execute("DELETE FROM context_nodes WHERE title LIKE 'FIX1 %%'")
            cur.execute("DELETE FROM groups WHERE id = %s", (GRUPPE,))
        c.commit()

    aufraeumen()
    yield c
    c.rollback()
    aufraeumen()
    c.close()


def _chat(conn, owner=ICH):
    cid = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO conversations (id, pseudonym, model_used, title) VALUES (%s, %s, 'test', 'FIX1 Chat')",
                    (str(cid), owner))
    conn.commit()
    return cid


def _knoten(conn, titel, *, owner=TEACHER1_PSEUDO, scope="school", status="active", gruppe=None):
    nid = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO context_nodes (id, category, content_type, title, content, read_scope, write_scope,"
            " owner_pseudonym, status, read_scope_group_id) VALUES (%s, 'artifact', 'arbeitsblatt', %s, %s, %s,"
            " 'private', %s, %s, %s)",
            (str(nid), f"FIX1 {titel}", f"Inhalt {titel}", scope, owner, status, gruppe))
    conn.commit()
    return nid


def _user(pseudonym, *rollen):
    return JwtPayload(sub=pseudonym, roles=list(rollen), grade=None, jti="j", iat=0, exp=2**31)


async def _anheften_und_kontext(async_engine, chat, user, ids):
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with fabrik() as db:
        zahl = await knoten_beim_anlegen_anheften(db, chat, user, ids)
        with patch("app.context.service.vektor_oder_none", AsyncMock(return_value=None)), \
             patch("app.context.search.vektor_oder_none", AsyncMock(return_value=None)):
            text = (await kontext_fuer_frage(None, user.sub, "Hilf mir", chat, db, rollen=user.roles)).text
        await db.commit()
    return zahl, text


async def test_lehrkraft_lesbare_aktive_knoten_vor_dem_kontext(conn, async_engine):
    chat = _chat(conn)
    lesbar = _knoten(conn, "Schulweit")
    privat_fremd = _knoten(conn, "Fremd privat", scope="private")
    archiviert = _knoten(conn, "Archiviert", status="archived")

    zahl, text = await _anheften_und_kontext(
        async_engine, chat, _user(ICH, "teacher"), [lesbar, privat_fremd, archiviert, lesbar, uuid.uuid4()])

    assert zahl == 1
    assert "FIX1 Schulweit" in text and "Inhalt Schulweit" in text
    assert "FIX1 Fremd privat" not in text and "FIX1 Archiviert" not in text


async def test_schuelerin_heftet_an_was_sie_lesen_darf(conn, async_engine):
    """Rollenoffen seit 0.41 — die Leseprüfung bleibt: Stundenentwürfe (`group_teachers`) nie."""
    chat = _chat(conn, owner=STUDENT_PSEUDO)
    lesbar = _knoten(conn, "Schulweit")
    # Die Schüler:in ist Mitglied der Gruppe — trotzdem kein Stundenentwurf.
    with conn.cursor() as cur:
        cur.execute("INSERT INTO groups (id, name, slug, type) VALUES (%s, 'fix1', 'fix1', 'teaching_group')",
                    (GRUPPE,))
        cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft)"
                    " VALUES (%s, %s, 'student', 'manuell')", (GRUPPE, STUDENT_PSEUDO))
    conn.commit()
    lehrkraft = _knoten(conn, "Nur Lehrkräfte", scope="group_teachers", gruppe=GRUPPE)
    zahl, text = await _anheften_und_kontext(
        async_engine, chat, _user(STUDENT_PSEUDO, "student"), [lesbar, lehrkraft])
    assert zahl == 1
    assert "FIX1 Schulweit" in text and "FIX1 Nur Lehrkräfte" not in text


async def test_schuelerin_ueber_die_schnittstelle(test_client, auth_headers_student, conn):
    chat = _chat(conn, owner=STUDENT_PSEUDO)
    lesbar, privat = _knoten(conn, "Schulweit"), _knoten(conn, "Fremd privat", scope="private")
    pfad = f"/context/conversations/{chat}/nodes"

    ok = await test_client.post(pfad, json={"node_id": str(lesbar)}, headers=auth_headers_student)
    verboten = await test_client.post(pfad, json={"node_id": str(privat)}, headers=auth_headers_student)
    liste = await test_client.get(pfad, headers=auth_headers_student)
    weg = await test_client.delete(f"{pfad}/{lesbar}", headers=auth_headers_student)

    assert (ok.status_code, verboten.status_code, weg.status_code) == (201, 403, 204)
    assert [n["node_id"] for n in liste.json()] == [str(lesbar)]


async def test_vorschau_heftet_nur_an_vorschau_chats(test_client, jwt_service, conn):
    import time
    from app.auth.vorschau import Vorschau

    echt = _chat(conn)
    vorschau_chat = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO conversations (id, pseudonym, model_used, title, preview_context) "
                    "VALUES (%s, %s, 'test', 'FIX1 Chat', '{\"jahrgang\": \"8\"}')", (str(vorschau_chat), ICH))
    conn.commit()
    lesbar = _knoten(conn, "Schulweit")
    jetzt = int(time.time())
    token, _ = jwt_service.issue(
        pseudonym=ICH, roles=["student"], grade="8",
        preview=Vorschau(echte_rollen=["teacher"], beginn=jetzt, sitzung_ablauf=jetzt + 3600), exp=jetzt + 3600)
    kopf = {"Cookie": f"session={token}"}

    im_vorschau_chat = await test_client.post(f"/context/conversations/{vorschau_chat}/nodes",
                                              json={"node_id": str(lesbar)}, headers=kopf)
    im_echten_chat = await test_client.post(f"/context/conversations/{echt}/nodes",
                                            json={"node_id": str(lesbar)}, headers=kopf)
    assert (im_vorschau_chat.status_code, im_echten_chat.status_code) == (201, 403)


async def test_chat_heftet_vor_dem_kontextaufbau_an():
    quelle = (Path(__file__).resolve().parents[2] / "app" / "chat" / "router.py").read_text(encoding="utf-8")
    assert 0 < quelle.index("knoten_beim_anlegen_anheften(db, conversation_id") \
        < quelle.index("kontext = await kontext_fuer_frage(")
