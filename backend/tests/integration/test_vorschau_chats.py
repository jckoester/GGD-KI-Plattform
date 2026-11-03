"""Vorschau-Chats (0.29, Schritt 4, ADR-016 F2 a). Erfordert TEST_DATABASE_URL."""
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.vorschau import Vorschau
from app.crons.cleanup_service import cleanup_stale_conversations
from app.db.models import Conversation, ConversationFlag, Group, GroupMembership, Message, Subject
from tests.integration.conftest import TEACHER1_PSEUDO

pytestmark = pytest.mark.asyncio

KRISE = "Ich will mich umbringen."


class _BisHierher(Exception):
    pass


@pytest_asyncio.fixture
async def fabrik(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def welt(fabrik):
    """Eine Unterrichtsgruppe der Lehrkraft, ein gewöhnlicher und ein Vorschau-Chat."""
    kennung = uuid.uuid4().hex[:8]
    async with fabrik() as db:
        fach = Subject(slug=f"vc-{kennung}", name="Vorschauchatfach")
        db.add(fach)
        await db.flush()
        g = Group(name="VC 9a", slug=f"vc-{kennung}", type="teaching_group", subject_id=fach.id)
        db.add(g)
        await db.flush()
        db.add(GroupMembership(group_id=g.id, pseudonym=TEACHER1_PSEUDO,
                               role_in_group="teacher", herkunft="eigen"))
        echt = Conversation(pseudonym=TEACHER1_PSEUDO, model_used="chat-standard",
                            title=f"Echt {kennung}")
        probe = Conversation(pseudonym=TEACHER1_PSEUDO, model_used="chat-standard",
                             title=f"Probe {kennung}",
                             preview_context={"jahrgang": "9", "gruppe_id": g.id})
        db.add_all([echt, probe])
        await db.flush()
        db.add_all([Message(conversation_id=echt.id, role="user", content="echt"),
                    Message(conversation_id=probe.id, role="user", content="probe")])
        await db.commit()
        return {"g": g.id, "echt": str(echt.id), "probe": str(probe.id)}


def _kopf(jwt_service, gruppe=None, *, normal=False):
    if normal:
        token, _ = jwt_service.issue(pseudonym=TEACHER1_PSEUDO, roles=["teacher"], grade=None)
    else:
        jetzt = int(time.time())
        token, _ = jwt_service.issue(
            pseudonym=TEACHER1_PSEUDO, roles=["student"], grade="9",
            preview=Vorschau(echte_rollen=["teacher"], gruppe_id=gruppe, beginn=jetzt,
                             sitzung_ablauf=jetzt + 3600),
            exp=jetzt + 3600,
        )
    return {"Cookie": f"session={token}"}


async def _neuer_chat(client, kopf, **json):
    """`POST /chat` bis zum Kontext; gibt die Konversation und ihre Krisen-Flags zurück."""
    gesehen = {}

    async def anhalten(*, chat_id, db, **_):
        gesehen["konversation"] = await db.get(Conversation, chat_id)
        gesehen["sql_null"] = (await db.execute(sa.select(
            Conversation.preview_context.is_(None)).where(Conversation.id == chat_id))).scalar_one()
        gesehen["flags"] = (await db.execute(sa.select(ConversationFlag).where(
            ConversationFlag.conversation_id == chat_id))).scalars().all()
        raise _BisHierher

    with patch("app.chat.router.kontext_fuer_frage", AsyncMock(side_effect=anhalten)):
        try:
            antwort = await client.post("/chat", headers=kopf, json={
                "messages": [{"role": "user", "content": KRISE}], **json})
        except _BisHierher:
            return gesehen, None
    return gesehen, antwort


async def test_neuer_chat_traegt_den_kontext_und_kein_flag(test_client, jwt_service, welt):
    gesehen, antwort = await _neuer_chat(test_client, _kopf(jwt_service, welt["g"]),
                                         group_id=welt["g"])
    assert antwort is None, antwort.text if antwort else ""
    assert gesehen["konversation"].preview_context["jahrgang"] == "9"
    assert gesehen["konversation"].preview_context["gruppe_id"] == welt["g"]
    assert gesehen["flags"] == [], "Ein Vorschau-Chat löst kein Krisen-Flag aus"


async def test_gegenprobe_gewoehnlicher_chat_flaggt(test_client, jwt_service, welt):
    gesehen, _ = await _neuer_chat(test_client, _kopf(jwt_service, normal=True))
    assert gesehen["konversation"].preview_context is None
    # ⚠️ In der Datenbank SQL-NULL, nicht JSON-`null`: Python liest beides als None, die
    # Listen und der Löschlauf fragen aber `IS NULL` (0.29.0: alle neuen Chats galten in SQL
    # als Vorschau-Chats und fehlten in „Letzte Chats“).
    assert gesehen["sql_null"] is True
    assert len(gesehen["flags"]) == 1


async def test_testchat_gibt_es_in_der_vorschau_nicht(test_client, jwt_service, welt):
    _, antwort = await _neuer_chat(test_client, _kopf(jwt_service, welt["g"]), is_test=True)
    assert antwort is not None and antwort.status_code == 422


async def test_fortsetzen_nur_in_derselben_welt(test_client, jwt_service, welt):
    _, draussen = await _neuer_chat(test_client, _kopf(jwt_service, normal=True),
                                    conversation_id=welt["probe"])
    assert draussen is not None and draussen.status_code == 409
    _, drinnen = await _neuer_chat(test_client, _kopf(jwt_service, welt["g"]),
                                   conversation_id=welt["echt"])
    assert drinnen is not None and drinnen.status_code == 404


async def test_listen(test_client, jwt_service, welt):
    async def ids(kopf, **params):
        antwort = await test_client.get("/conversations", headers=kopf,
                                        params={"limit": 100, **params})
        return {x["id"] for x in antwort.json()["items"]}

    normal = _kopf(jwt_service, normal=True)
    assert welt["echt"] in await ids(normal) and welt["probe"] not in await ids(normal)
    vorschauliste = await ids(normal, vorschau="true")
    assert welt["probe"] in vorschauliste and welt["echt"] not in vorschauliste
    drinnen = await ids(_kopf(jwt_service, welt["g"]))
    assert welt["probe"] in drinnen and welt["echt"] not in drinnen


async def test_einzelner_chat(test_client, jwt_service, welt):
    drinnen = _kopf(jwt_service, welt["g"])
    echt = f"/conversations/{welt['echt']}"
    probe = f"/conversations/{welt['probe']}"
    assert (await test_client.get(f"{echt}/messages", headers=drinnen)).status_code == 403
    assert (await test_client.patch(echt, headers=drinnen, json={"title": "x"})).status_code == 403
    assert (await test_client.patch(probe, headers=drinnen, json={"title": "Umbenannt"})).status_code == 200
    # Außerhalb der Vorschau lesen und löschen — die eigene Liste „Vorschau“.
    normal = _kopf(jwt_service, normal=True)
    assert (await test_client.get(f"{probe}/messages", headers=normal)).status_code == 200
    assert (await test_client.delete(probe, headers=normal)).status_code == 204


async def test_rueckmeldung_aus_der_vorschau(test_client, jwt_service, welt, fabrik):
    drinnen = _kopf(jwt_service, welt["g"])
    inhalt = f"Aus der Vorschau, Test {uuid.uuid4().hex[:6]}."
    antwort = await test_client.post("/feedback", headers=drinnen, json={
        "category": "bug", "content": inhalt, "app_version": "0.29.0",
        "active_conversation_id": welt["probe"]})
    assert antwort.status_code == 201, antwort.text
    async with fabrik() as db:
        rolle, vorschau = (await db.execute(sa.text(
            "SELECT role, preview FROM feedback WHERE content = :c"), {"c": inhalt})).one()
    assert (rolle, vorschau) == ("teacher", True), "Es meldet eine Lehrkraft, aus der Vorschau"
    # Den echten Chat hängt die Vorschau nicht an.
    angehaengt = await test_client.post("/feedback", headers=drinnen, json={
        "category": "bug", "content": inhalt + " Mit Anhang.", "app_version": "0.29.0",
        "attach_conversation_id": welt["echt"]})
    assert angehaengt.status_code == 404


@pytest_asyncio.fixture
async def db_ohne_commit(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()
    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


async def test_vorschau_chats_gehen_nach_30_tagen(db_ohne_commit):
    db = db_ohne_commit
    jetzt = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    vor_40 = jetzt - timedelta(days=40)
    alt_probe = Conversation(pseudonym="vc-frist", model_used="m", last_message_at=vor_40,
                             preview_context={"jahrgang": "9"})
    alt_echt = Conversation(pseudonym="vc-frist", model_used="m", last_message_at=vor_40)
    frisch_probe = Conversation(pseudonym="vc-frist", model_used="m",
                                last_message_at=jetzt - timedelta(days=10),
                                preview_context={"jahrgang": "9"})
    db.add_all([alt_probe, alt_echt, frisch_probe])
    await db.flush()
    await cleanup_stale_conversations(db, now=jetzt)
    uebrig = set((await db.execute(sa.select(Conversation.id).where(
        Conversation.pseudonym == "vc-frist"))).scalars().all())
    assert alt_probe.id not in uebrig
    assert alt_echt.id in uebrig, "Gewöhnliche Chats behalten ihre 93 Tage"
    assert frisch_probe.id in uebrig
