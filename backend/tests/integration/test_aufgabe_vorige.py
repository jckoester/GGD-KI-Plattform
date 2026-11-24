"""Aufgaben-Weiterleitung (Plan „Freier Schüler-Chat“, 7a): Kam die letzte sichtbare Antwort vom
Zielmodell? Die Abfrage gegen die echte Datenbank — samt Spalte aus Migration 0113, ausgeblendeten
Nachrichten und der Antwort, die eine Bearbeitung gerade ersetzt. Dazu das Feld in der
Nachrichten-API, an dem die Oberfläche den Trenner entscheidet."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.chat.router import _vorige_weitergeleitet
from app.db.models import Conversation, Message
from tests.integration.conftest import TEACHER1_PSEUDO

pytestmark = pytest.mark.asyncio

T0 = datetime(2026, 11, 24, 8, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def gespraech(async_engine):
    """Zug 1 weitergeleitet, Zug 2 nicht, Zug 3 weitergeleitet, aber ausgeblendet (bearbeitet)."""
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    ids = {}
    async with factory() as s:
        konv = Conversation(id=uuid4(), pseudonym=TEACHER1_PSEUDO, model_used="chat-standard")
        s.add(konv)
        await s.flush()
        for nr, (modell, von, ersetzt) in enumerate((
            ("chat-komplex", "chat-standard", None),
            ("chat-standard", None, None),
            ("chat-komplex", "chat-standard", T0),
        ), start=1):
            zeit = T0 + timedelta(minutes=nr)
            s.add(Message(conversation_id=konv.id, role="user", content=f"Frage {nr}", created_at=zeit))
            antwort = Message(conversation_id=konv.id, role="assistant", content=f"Antwort {nr}",
                              created_at=zeit, model=modell, weitergeleitet_von=von, ersetzt_am=ersetzt)
            s.add(antwort)
            await s.flush()
            ids[nr] = antwort.id
        await s.commit()
        konv_id = konv.id
    yield konv_id, ids
    async with factory() as s:
        await s.execute(delete(Conversation).where(Conversation.id == konv_id))
        await s.commit()


async def test_letzte_sichtbare_antwort_zaehlt(db_session, gespraech):
    konv, ids = gespraech
    # Zug 3 ist ausgeblendet, sichtbar zuletzt: Zug 2, nicht weitergeleitet.
    assert await _vorige_weitergeleitet(db_session, konv, []) is False
    # Ersetzt die Bearbeitung Zug 2, gilt Zug 1 — weitergeleitet.
    assert await _vorige_weitergeleitet(db_session, konv, [ids[2]]) is True


async def test_ohne_antwort_keine_vorige(db_session):
    assert await _vorige_weitergeleitet(db_session, uuid4(), []) is False


async def test_nachrichten_api_liefert_das_ausgangsmodell(test_client, auth_headers, gespraech):
    konv, _ = gespraech
    resp = await test_client.get(f"/conversations/{konv}/messages", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    antworten = [m for m in resp.json()["messages"] if m["role"] == "assistant"]
    assert [(m["model"], m["weitergeleitet_von"]) for m in antworten] == [
        ("chat-komplex", "chat-standard"), ("chat-standard", None)]
