"""Produkte im Chat (0.41, Päckchen AN, Schritt 10): anhängen, ablösen, im Prompt.

Gegen echtes Postgres: `/artifacts/anhaengbar`, `/artifacts/chats/{id}` und
`kontext_fuer_frage` (der Abschnitt „Explizit hinzugefügter Kontext“).
"""
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import psycopg2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.artifacts import im_chat
from app.auth.vorschau import Vorschau
from app.context.service import kontext_fuer_frage
from tests.integration.conftest import STUDENT_PSEUDO, TEACHER1_PSEUDO, TEACHER2_PSEUDO

pytestmark = pytest.mark.asyncio

ICH = TEACHER2_PSEUDO
JETZT = datetime.now(timezone.utc)


@pytest.fixture
def conn(db_url, run_migrations):
    c = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    leute = [ICH, TEACHER1_PSEUDO, STUDENT_PSEUDO]

    def aufraeumen():
        with c.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE pseudonym = ANY(%s) AND title LIKE 'AN10%%'", (leute,))
            cur.execute("DELETE FROM artifacts WHERE owner_pseudonym = ANY(%s)", (leute,))
        c.commit()

    aufraeumen()
    yield c
    c.rollback()
    aufraeumen()
    c.close()


def _chat(conn, owner=ICH, vorschau=False):
    cid = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO conversations (id, pseudonym, model_used, title, preview_context) "
            "VALUES (%s, %s, 'test', 'AN10 Chat', %s)",
            (str(cid), owner, '{"jahrgang": "8"}' if vorschau else None),
        )
    conn.commit()
    return str(cid)


def _produkt(conn, titel="Arbeitsblatt Redox", *, kind="document", quelle="# Redox\n\nAufgabe 1: Oxidation",
             owner=ICH, abgeleitet=None, minuten=0):
    pid = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO artifacts (id, owner_pseudonym, kind, mime_type, byte_size, title, source, derived_from,"
            " created_at, updated_at, expires_at) VALUES (%s, %s, %s, 'text/markdown', 10, %s, %s, %s, %s, %s, %s)",
            (str(pid), owner, kind, titel, quelle, abgeleitet, JETZT - timedelta(minutes=minuten),
             JETZT - timedelta(minutes=minuten), JETZT + timedelta(days=300)),
        )
    conn.commit()
    return str(pid)


async def _kontext(async_engine, chat_id, pseudonym=ICH):
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    with patch("app.context.service.vektor_oder_none", AsyncMock(return_value=None)), \
         patch("app.context.search.vektor_oder_none", AsyncMock(return_value=None)):
        async with fabrik() as db:
            k = await kontext_fuer_frage(None, pseudonym, "Ergänze eine Aufgabe", uuid.UUID(chat_id), db,
                                         rollen=["teacher"])
    return k.text


async def test_anhaengbar_nur_eigene_mit_quelle(test_client, auth_headers_teacher2, conn):
    dok = _produkt(conn, "Redox Blatt", minuten=5)
    diagramm = _produkt(conn, "Redox Fluss", kind="mermaid", quelle="flowchart LR\n A-->B", minuten=1)
    _produkt(conn, "Redox Bild", kind="image", quelle="ein Bild")
    _produkt(conn, "Redox leer", quelle="  ")
    _produkt(conn, "Redox Export", kind="export_pdf", abgeleitet=dok)
    _produkt(conn, "Redox fremd", owner=TEACHER1_PSEUDO)

    resp = await test_client.get("/artifacts/anhaengbar", params={"q": "redox"}, headers=auth_headers_teacher2)

    assert resp.status_code == 200, resp.text
    assert [i["artifact_id"] for i in resp.json()] == [diagramm, dok]


async def test_anhaengen_auflisten_abhaengen(test_client, auth_headers_teacher2, conn):
    chat, dok = _chat(conn), _produkt(conn)
    pfad = f"/artifacts/chats/{chat}"

    erst = await test_client.post(pfad, json={"artifact_id": dok}, headers=auth_headers_teacher2)
    zweit = await test_client.post(pfad, json={"artifact_id": dok}, headers=auth_headers_teacher2)
    assert (erst.status_code, zweit.status_code) == (201, 201)
    liste = (await test_client.get(pfad, headers=auth_headers_teacher2)).json()
    assert [(i["artifact_id"], i["title"]) for i in liste] == [(dok, "Arbeitsblatt Redox")]

    weg = await test_client.delete(f"{pfad}/{dok}", headers=auth_headers_teacher2)
    assert weg.status_code == 204
    assert (await test_client.get(pfad, headers=auth_headers_teacher2)).json() == []


async def test_fremdes_produkt_und_fremder_chat(test_client, auth_headers_teacher2, conn):
    eigener_chat, fremder_chat = _chat(conn), _chat(conn, owner=TEACHER1_PSEUDO)
    eigenes, fremdes = _produkt(conn), _produkt(conn, owner=TEACHER1_PSEUDO)

    r1 = await test_client.post(f"/artifacts/chats/{eigener_chat}", json={"artifact_id": fremdes},
                                headers=auth_headers_teacher2)
    r2 = await test_client.post(f"/artifacts/chats/{fremder_chat}", json={"artifact_id": eigenes},
                                headers=auth_headers_teacher2)
    assert (r1.status_code, r2.status_code) == (403, 404)


async def test_bild_laesst_sich_nicht_anhaengen(test_client, auth_headers_teacher2, conn):
    chat, bild = _chat(conn), _produkt(conn, kind="image", quelle="ein Bild")
    resp = await test_client.post(f"/artifacts/chats/{chat}", json={"artifact_id": bild},
                                  headers=auth_headers_teacher2)
    assert resp.status_code == 422


async def test_schuelerin_kann_anhaengen(test_client, auth_headers_student, conn):
    """Für Schüler:innen ist das seit Schritt 9 der Weg, eigene Arbeit mitzugeben."""
    chat, dok = _chat(conn, owner=STUDENT_PSEUDO), _produkt(conn, owner=STUDENT_PSEUDO)
    resp = await test_client.post(f"/artifacts/chats/{chat}", json={"artifact_id": dok},
                                  headers=auth_headers_student)
    assert resp.status_code == 201, resp.text


async def test_vorschau_haengt_nichts_an(test_client, jwt_service, conn):
    chat, dok = _chat(conn, vorschau=True), _produkt(conn)
    jetzt = int(time.time())
    token, _ = jwt_service.issue(
        pseudonym=ICH, roles=["student"], grade="8",
        preview=Vorschau(echte_rollen=["teacher"], beginn=jetzt, sitzung_ablauf=jetzt + 3600),
        exp=jetzt + 3600,
    )
    resp = await test_client.post(f"/artifacts/chats/{chat}", json={"artifact_id": dok},
                                  headers={"Cookie": f"session={token}"})
    assert resp.status_code == 403


async def test_quelle_steht_im_prompt(test_client, auth_headers_teacher2, conn, async_engine):
    chat = _chat(conn)
    dok = _produkt(conn)
    diagramm = _produkt(conn, "Ablauf", kind="mermaid", quelle="flowchart LR\n A-->B")
    for pid in (dok, diagramm):
        await test_client.post(f"/artifacts/chats/{chat}", json={"artifact_id": pid},
                               headers=auth_headers_teacher2)

    text = await _kontext(async_engine, chat)

    assert "## Explizit hinzugefügter Kontext" in text
    assert "### Arbeitsblatt Redox — Dokument aus der eigenen Werkstatt\n# Redox\n\nAufgabe 1: Oxidation" in text
    assert "### Ablauf — Diagramm (Mermaid) aus der eigenen Werkstatt\n```mermaid\nflowchart LR\n A-->B\n```" in text


async def test_geloeschtes_produkt_faellt_weg_chat_bleibt(test_client, auth_headers_teacher2, conn, async_engine):
    chat, dok = _chat(conn), _produkt(conn)
    await test_client.post(f"/artifacts/chats/{chat}", json={"artifact_id": dok}, headers=auth_headers_teacher2)

    await test_client.delete(f"/artifacts/{dok}", headers=auth_headers_teacher2)

    assert (await test_client.get(f"/artifacts/chats/{chat}", headers=auth_headers_teacher2)).json() == []
    assert "Arbeitsblatt Redox" not in await _kontext(async_engine, chat)


async def test_lange_quelle_wird_gekuerzt(test_client, auth_headers_teacher2, conn, async_engine):
    chat = _chat(conn)
    dok = _produkt(conn, quelle="x" * (im_chat.MAX_ZEICHEN + 500))
    await test_client.post(f"/artifacts/chats/{chat}", json={"artifact_id": dok}, headers=auth_headers_teacher2)

    text = await _kontext(async_engine, chat)

    assert "x" * im_chat.MAX_ZEICHEN in text
    assert "x" * (im_chat.MAX_ZEICHEN + 1) not in text
    assert im_chat.GEKUERZT in text


async def test_fremder_anhang_kommt_nie_in_den_prompt(conn, async_engine):
    """Zweite Sicherung: Selbst ein Anhang, der an der Schnittstelle vorbei entstand, bleibt draußen."""
    chat, fremdes = _chat(conn), _produkt(conn, "Fremdes Blatt", owner=TEACHER1_PSEUDO)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO chat_artifacts (chat_id, artifact_id) VALUES (%s, %s)", (chat, fremdes))
    conn.commit()
    assert "Fremdes Blatt" not in await _kontext(async_engine, chat)


async def test_beim_anlegen_vor_dem_kontext(conn, async_engine):
    """„Im Chat verwenden“ startet einen neuen Chat — die erste Antwort muss das Produkt sehen."""
    chat = _chat(conn)
    eigenes, fremdes = _produkt(conn), _produkt(conn, "Fremdes Blatt", owner=TEACHER1_PSEUDO)
    bild = _produkt(conn, "Bild", kind="image", quelle="ein Bild")
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with fabrik() as db:
        zahl = await im_chat.beim_anlegen_anhaengen(
            db, uuid.UUID(chat), ICH, [uuid.UUID(eigenes), uuid.UUID(fremdes), uuid.UUID(bild), uuid.UUID(eigenes)])
        # Noch nicht committet — und doch im Kontext derselben Sitzung.
        with patch("app.context.service.vektor_oder_none", AsyncMock(return_value=None)), \
             patch("app.context.search.vektor_oder_none", AsyncMock(return_value=None)):
            text = (await kontext_fuer_frage(None, ICH, "Hilf mir", uuid.UUID(chat), db, rollen=["teacher"])).text
        await db.commit()
    assert zahl == 1
    assert "Arbeitsblatt Redox" in text and "Fremdes Blatt" not in text


async def test_chat_haengt_vor_dem_kontextaufbau_an():
    """Reihenfolge im Chat-Handler: erst anhängen, dann `kontext_fuer_frage`."""
    from pathlib import Path

    quelle = (Path(__file__).resolve().parents[2] / "app" / "chat" / "router.py").read_text(encoding="utf-8")
    assert 0 < quelle.index("im_chat.beim_anlegen_anhaengen(") < quelle.index("kontext = await kontext_fuer_frage(")
