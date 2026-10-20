"""Letzte Nachricht bearbeiten und Antwort abbrechen (0.19, Schritt 5).

Ersetzen heißt ausblenden, nicht löschen (Plan F5): An der alten Nachricht hängen per CASCADE
die Krisenmeldung, Bausteine und Bilder. Ein Abbruch speichert den Zug mit dem Teil der Antwort,
der bis dahin da war — bis 0.19 ging er ganz verloren.
"""
import asyncio
from unittest.mock import AsyncMock, patch
from uuid import UUID

import psycopg2
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.chat import router
from app.db.models import Conversation, ConversationFlag, Message
from tests.integration.conftest import TEACHER1_PSEUDO


@pytest.fixture(autouse=True)
def _aufraeumen(db_url, run_migrations):
    yield
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("DELETE FROM conversations WHERE title = 'Ersetzen-Probe'")
    conn.commit()
    conn.close()


@pytest.fixture
def sitzungen(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def _konversation(sitzungen) -> UUID:
    async with sitzungen() as db:
        konv = Conversation(pseudonym=TEACHER1_PSEUDO, model_used="model-x", title="Ersetzen-Probe")
        db.add(konv)
        await db.commit()
        return konv.id


async def _zug(sitzungen, konv, frage, antwort, **kw):
    async with sitzungen() as db:
        return await router._persist(db, konv, frage, [], antwort, {}, "model-x", **kw)


async def _sichtbar(test_client, auth_headers, konv):
    resp = await test_client.get(f"/conversations/{konv}/messages", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    return [(m["role"], m["content"]) for m in resp.json()["messages"]]


@pytest.mark.asyncio
async def test_ersetzen_blendet_frage_und_antwort_aus(sitzungen, test_client, auth_headers):
    konv = await _konversation(sitzungen)
    await _zug(sitzungen, konv, "erste", "A1")
    await _zug(sitzungen, konv, "zweite", "A2")
    async with sitzungen() as db:
        ersetzen = await router.zu_ersetzende_nachrichten(db, konv)
    assert len(ersetzen) == 2

    await _zug(sitzungen, konv, "zweite, besser", "A2'", ersetze_ids=ersetzen)

    assert await _sichtbar(test_client, auth_headers, konv) == [
        ("user", "erste"), ("assistant", "A1"), ("user", "zweite, besser"), ("assistant", "A2'"),
    ]
    async with sitzungen() as db:
        alle = (await db.execute(sa.select(Message).where(Message.conversation_id == konv))).scalars().all()
    assert len(alle) == 6, "ausgeblendet, nicht gelöscht"


@pytest.mark.asyncio
async def test_zweimal_bearbeiten_ersetzt_die_zuletzt_geschriebene(sitzungen):
    konv = await _konversation(sitzungen)
    await _zug(sitzungen, konv, "v1", "A")
    async with sitzungen() as db:
        erste = await router.zu_ersetzende_nachrichten(db, konv)
    await _zug(sitzungen, konv, "v2", "B", ersetze_ids=erste)
    async with sitzungen() as db:
        zweite = await router.zu_ersetzende_nachrichten(db, konv)
        inhalte = (await db.execute(sa.select(Message.content).where(Message.id.in_(zweite)))).scalars().all()
    assert sorted(inhalte) == ["B", "v2"]


@pytest.mark.asyncio
async def test_ohne_nachricht_nichts_zu_ersetzen(sitzungen):
    konv = await _konversation(sitzungen)
    async with sitzungen() as db:
        assert await router.zu_ersetzende_nachrichten(db, konv) == []


@pytest.mark.asyncio
async def test_krisenmeldung_an_der_ersetzten_nachricht_bleibt(sitzungen):
    """ADR-008: Die Meldung hängt per CASCADE an der Nachricht — Löschen nähme sie mit."""
    konv = await _konversation(sitzungen)
    await _zug(sitzungen, konv, "heikel", "Antwort")
    async with sitzungen() as db:
        frage = (await db.execute(sa.select(Message.id).where(
            Message.conversation_id == konv, Message.role == "user"))).scalar_one()
        db.add(ConversationFlag(conversation_id=konv, message_id=frage, flag_category="selbstgefaehrdung",
                                flag_source="auto_crisis", severity="alert", trigger_rule="probe"))
        await db.commit()
        ersetzen = await router.zu_ersetzende_nachrichten(db, konv)
    await _zug(sitzungen, konv, "harmlos", "Antwort 2", ersetze_ids=ersetzen)
    async with sitzungen() as db:
        flags = (await db.execute(sa.select(ConversationFlag.message_id).where(
            ConversationFlag.conversation_id == konv))).scalars().all()
    assert flags == [frage]


@pytest.mark.asyncio
async def test_neue_unterhaltung_kann_nichts_ersetzen(test_client, auth_headers):
    resp = await test_client.post("/chat", headers=auth_headers, json={
        "messages": [{"role": "user", "content": "x"}], "ersetzt_letzte": True})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_abbruch_speichert_frage_teilantwort_und_kosten(sitzungen, test_client, auth_headers):
    """Was der abgebrochene Generator anstößt, landet gespeichert und als abgebrochen markiert —
    samt Kosten-Nachtrag für die gelaufenen Anfragen."""
    konv = await _konversation(sitzungen)
    offen = AsyncMock()
    client = AsyncMock()
    with patch.object(router, "AsyncSessionLocal", sitzungen), \
         patch.object(router, "anbietermodell", AsyncMock(return_value="anbieter/x")), \
         patch.object(router.kosten_nachtrag, "nachtragen") as nachtrag:
        router._abbruch_sichern(
            conversation_id=konv, user_message="lange Frage", attachments=[],
            teilantwort="Der Anfang der Ant", usage={}, model_used="model-x",
            deployment_id=None, request_ids=["req-1"], image_cost=0.0,
            offen=[offen], client=client, skip_user_message=False, assistant_id=None,
            conv_assistant_update=None, generated_image_ids=[], bausteine=[],
            ersetze_ids=[], werkzeuge_mit_wirkung=["update_lesson_phases"],
        )
        for _ in range(50):
            await asyncio.sleep(0.02)
            if nachtrag.called:
                break

    assert nachtrag.called and nachtrag.call_args.kwargs["request_ids"] == ["req-1"]
    offen.aclose.assert_awaited()
    client.aclose.assert_awaited()
    resp = await test_client.get(f"/conversations/{konv}/messages", headers=auth_headers)
    nachrichten = resp.json()["messages"]
    assert [(m["role"], m["content"]) for m in nachrichten] == [
        ("user", "lange Frage"), ("assistant", "Der Anfang der Ant")]
    assert nachrichten[1]["abgebrochen"] is True
    assert nachrichten[1]["werkzeuge_mit_wirkung"] == ["update_lesson_phases"]
    assert nachrichten[1]["cost_status"] == "ausstehend"
