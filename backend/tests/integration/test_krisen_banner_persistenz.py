"""Das Hilfe-Banner überlebt das Neuladen (ADR-008 Teil 3/4).

Bis 09/2026 kam es **nur** live über SSE. Wer die Konversation neu lud, sah die
Kontaktadressen nicht mehr — genau in dem Moment, in dem sie gebraucht würden.

Gespeichert wird dafür **nichts Neues**: Das Krisen-Flag zeigt mit `message_id`
bereits auf die auslösende Nachricht.
"""
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, ConversationFlag, Message
from tests.integration.conftest import TEACHER1_PSEUDO

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def gespraech(async_engine):
    """Ein Gespräch mit zwei Treffern derselben Kategorie und einem einer zweiten."""
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    ids = {}
    async with factory() as s:
        conv = Conversation(id=uuid4(), pseudonym=TEACHER1_PSEUDO, model_used="gpt-4o")
        s.add(conv)
        await s.flush()
        ids["conversation"] = conv.id

        for name, rolle, inhalt in (
            ("erste_frage", "user", "Niemand mag mich in der Klasse."),
            ("erste_antwort", "assistant", "Das klingt belastend."),
            ("zweite_frage", "user", "Wieder: niemand mag mich in der Klasse."),
            ("dritte_frage", "user", "Ich bin zu dick."),
        ):
            m = Message(conversation_id=conv.id, role=rolle, content=inhalt)
            s.add(m)
            await s.flush()
            ids[name] = m.id

        for nachricht, kategorie in (
            ("erste_frage", "mobbing"),
            ("zweite_frage", "mobbing"),
            ("dritte_frage", "essverhalten"),
        ):
            s.add(ConversationFlag(
                conversation_id=conv.id, message_id=ids[nachricht],
                flag_source="auto_crisis", flag_category=kategorie,
                severity="warning",
            ))
        await s.commit()

    yield ids

    async with factory() as s:
        await s.execute(delete(ConversationFlag).where(
            ConversationFlag.conversation_id == ids["conversation"]))
        await s.execute(delete(Message).where(
            Message.conversation_id == ids["conversation"]))
        await s.execute(delete(Conversation).where(
            Conversation.id == ids["conversation"]))
        await s.commit()


async def _laden(client, headers, conv_id):
    resp = await client.get(f"/conversations/{conv_id}/messages", headers=headers)
    assert resp.status_code == 200, resp.text
    return {m["id"]: m for m in resp.json()["messages"]}


async def test_banner_haengt_an_der_ausloesenden_nachricht(
    test_client, auth_headers, gespraech
):
    """An der Nutzer-Nachricht — nicht an der Antwort, die darauf folgte."""
    nachrichten = await _laden(test_client, auth_headers, gespraech["conversation"])
    ausloeser = nachrichten[str(gespraech["erste_frage"])]
    assert ausloeser["crisis"] is not None
    assert ausloeser["crisis"]["help_topic"] == "school_social"
    assert nachrichten[str(gespraech["erste_antwort"])]["crisis"] is None


async def test_banner_traegt_die_kontakte(test_client, auth_headers, gespraech):
    nachrichten = await _laden(test_client, auth_headers, gespraech["conversation"])
    banner = nachrichten[str(gespraech["erste_frage"])]["crisis"]
    assert banner["label"]
    assert banner["internal"] or banner["external"], "Banner ohne jede Anlaufstelle"


async def test_nur_der_erste_treffer_je_kategorie(test_client, auth_headers, gespraech):
    """Dieselbe Regel wie live: Wer sich wiederholt, wird nicht wiederholt belehrt."""
    nachrichten = await _laden(test_client, auth_headers, gespraech["conversation"])
    assert nachrichten[str(gespraech["zweite_frage"])]["crisis"] is None


async def test_eine_zweite_kategorie_bekommt_ein_eigenes_banner(
    test_client, auth_headers, gespraech
):
    nachrichten = await _laden(test_client, auth_headers, gespraech["conversation"])
    banner = nachrichten[str(gespraech["dritte_frage"])]["crisis"]
    assert banner is not None
    assert banner["help_topic"] == "eating"


async def test_unbekannte_kategorie_bricht_nichts(
    test_client, auth_headers, gespraech, async_engine
):
    """Die Kuratierung darf Regeln streichen — alte Fälle bleiben geflaggt.

    Ohne diese Zusage wäre jede gestrichene Regel ein 500er beim Öffnen der
    Konversation, in der sie einmal griff.

    ⚠️ Der Test prüft das **Verhalten**, nicht eine bestimmte Zeile: Zwei Prüfungen
    laufen hier zusammen (unbekannte Kategorie in `crisis_triggers.yaml`, fehlendes
    Thema in `help_resources.yaml`). Nimmt man eine heraus, bleibt der Test grün —
    nachgeprüft am 10.09.2026. Das ist in Ordnung, solange niemand glaubt, er
    schütze eine einzelne Bedingung.
    """
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        s.add(ConversationFlag(
            conversation_id=gespraech["conversation"],
            message_id=gespraech["erste_antwort"],
            flag_source="auto_crisis", flag_category="gibt_es_nicht_mehr",
            severity="info",
        ))
        await s.commit()

    nachrichten = await _laden(test_client, auth_headers, gespraech["conversation"])
    assert nachrichten[str(gespraech["erste_antwort"])]["crisis"] is None
