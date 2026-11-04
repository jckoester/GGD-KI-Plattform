"""Antwortbewertung (0.31, Päckchen T, Plan Schritt 4). Erfordert TEST_DATABASE_URL.

Jeder Test benutzt ein eigenes Modell-Kürzel — so trifft er nur seine eigenen Zählerzeilen,
auch wenn mehrere Tests in derselben Woche zählen.
"""
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.vorschau import Vorschau
from app.context.vorab_statistik import woche_von
from app.db.models import Assistant, Conversation, Message, MessageRating, RatingCount
from app.feedback.bewertung import bewerte
from tests.integration.conftest import STUDENT_PSEUDO, TEACHER1_PSEUDO

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def fabrik(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def chat(fabrik):
    """Ein Chat der Schüler:in mit Frage und Antwort; eigenes Modell-Kürzel je Test."""
    modell = f"t-bew-{uuid.uuid4().hex[:8]}"

    async def anlegen(*, pseudonym=STUDENT_PSEUDO, assistant_id=None, **konv):
        async with fabrik() as db:
            k = Conversation(pseudonym=pseudonym, model_used=modell, **konv)
            db.add(k)
            await db.flush()
            frage = Message(conversation_id=k.id, role="user", content="Frage")
            antwort = Message(conversation_id=k.id, role="assistant", content="Antwort",
                              model=modell, assistant_id=assistant_id)
            db.add_all([frage, antwort])
            await db.commit()
            return {"konv": k.id, "frage": frage.id, "antwort": antwort.id, "modell": modell}

    yield anlegen
    async with fabrik() as db:
        await db.execute(sa.delete(Conversation).where(Conversation.model_used == modell))
        await db.execute(sa.delete(RatingCount).where(RatingCount.modell == modell))
        await db.commit()


async def _zaehler(fabrik, modell):
    async with fabrik() as db:
        zeilen = (await db.execute(
            sa.select(RatingCount.rolle, RatingCount.plus, RatingCount.minus)
            .where(RatingCount.modell == modell).order_by(RatingCount.rolle)
        )).all()
    return [tuple(z) for z in zeilen]


async def _put(client, headers, mid, wert):
    return await client.put(f"/messages/{mid}/rating", headers=headers, json={"rating": wert})


# ── Setzen, umentscheiden, zurücknehmen ──────────────────────────────────────────

async def test_daumen_hoch_zaehlt(test_client, auth_headers_student, chat, fabrik):
    c = await chat()
    antwort = await _put(test_client, auth_headers_student, c["antwort"], 1)
    assert antwort.status_code == 200, antwort.text
    assert antwort.json() == {"rating": 1}
    assert await _zaehler(fabrik, c["modell"]) == [("student", 1, 0)]


async def test_zweimal_dasselbe_zaehlt_einmal(test_client, auth_headers_student, chat, fabrik):
    c = await chat()
    for _ in range(2):
        await _put(test_client, auth_headers_student, c["antwort"], -1)
    assert await _zaehler(fabrik, c["modell"]) == [("student", 0, 1)]


async def test_umentscheiden_und_zuruecknehmen(test_client, auth_headers_student, chat, fabrik):
    c = await chat()
    await _put(test_client, auth_headers_student, c["antwort"], 1)
    await _put(test_client, auth_headers_student, c["antwort"], -1)
    assert await _zaehler(fabrik, c["modell"]) == [("student", 0, 1)]
    antwort = await _put(test_client, auth_headers_student, c["antwort"], 0)
    assert antwort.json() == {"rating": None}
    assert await _zaehler(fabrik, c["modell"]) == [("student", 0, 0)]
    async with fabrik() as db:
        assert await db.get(MessageRating, c["antwort"]) is None


async def test_zuruecknehmen_ohne_bewertung_ist_nichts(test_client, auth_headers_student, chat, fabrik):
    c = await chat()
    antwort = await _put(test_client, auth_headers_student, c["antwort"], 0)
    assert antwort.status_code == 200 and antwort.json() == {"rating": None}
    assert await _zaehler(fabrik, c["modell"]) == []


async def test_lehrkraft_zaehlt_als_lehrkraft(test_client, auth_headers, chat, fabrik):
    """`auth_headers` ist Lehrkraft und Admin — zählt als Lehrkraft."""
    c = await chat(pseudonym=TEACHER1_PSEUDO)
    await _put(test_client, auth_headers, c["antwort"], 1)
    assert await _zaehler(fabrik, c["modell"]) == [("teacher", 1, 0)]


async def test_umentscheiden_bleibt_in_der_woche_der_ersten_bewertung(chat, fabrik):
    c = await chat()
    erst = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    async with fabrik() as db:
        await bewerte(db, pseudonym=STUDENT_PSEUDO, rollen=["student"], message_id=c["antwort"],
                      wert=1, jetzt=erst)
    async with fabrik() as db:
        await bewerte(db, pseudonym=STUDENT_PSEUDO, rollen=["student"], message_id=c["antwort"],
                      wert=-1, jetzt=erst + timedelta(days=10))
    async with fabrik() as db:
        zeilen = (await db.execute(sa.select(RatingCount.woche, RatingCount.plus, RatingCount.minus)
                                   .where(RatingCount.modell == c["modell"]))).all()
    assert [tuple(z) for z in zeilen] == [(woche_von(erst), 0, 1)]


# ── Was nicht geht ───────────────────────────────────────────────────────────────

async def test_fremde_nachricht_ist_unbekannt(test_client, auth_headers_teacher2, chat):
    c = await chat()
    assert (await _put(test_client, auth_headers_teacher2, c["antwort"], 1)).status_code == 404
    assert (await _put(test_client, auth_headers_teacher2, uuid.uuid4(), 1)).status_code == 404


async def test_nur_antworten(test_client, auth_headers_student, chat):
    c = await chat()
    assert (await _put(test_client, auth_headers_student, c["frage"], 1)).status_code == 422


async def test_ungueltiger_wert(test_client, auth_headers_student, chat):
    c = await chat()
    assert (await _put(test_client, auth_headers_student, c["antwort"], 2)).status_code == 422


async def test_ersetzte_antwort(test_client, auth_headers_student, chat, fabrik):
    c = await chat()
    async with fabrik() as db:
        await db.execute(sa.update(Message).where(Message.id == c["antwort"])
                         .values(ersetzt_am=datetime.now(timezone.utc)))
        await db.commit()
    assert (await _put(test_client, auth_headers_student, c["antwort"], 1)).status_code == 409


@pytest.mark.parametrize("konv", [{"is_test": True}, {"preview_context": {"jahrgang": "9"}}])
async def test_keine_daumen_in_test_und_vorschau_chats(test_client, auth_headers_student, chat,
                                                       fabrik, konv):
    c = await chat(**konv)
    assert (await _put(test_client, auth_headers_student, c["antwort"], 1)).status_code == 403
    assert await _zaehler(fabrik, c["modell"]) == []


async def test_in_der_vorschau_gesperrt(test_client, jwt_service, chat, fabrik):
    """Schreibsperre der Vorschau (0.29): Der Endpunkt steht nicht in `ERLAUBT`."""
    c = await chat(pseudonym=TEACHER1_PSEUDO, preview_context={"jahrgang": "9"})
    jetzt = int(time.time())
    token, _ = jwt_service.issue(
        pseudonym=TEACHER1_PSEUDO, roles=["student"], grade="9",
        preview=Vorschau(echte_rollen=["teacher"], beginn=jetzt, sitzung_ablauf=jetzt + 3600),
        exp=jetzt + 3600,
    )
    antwort = await _put(test_client, {"Cookie": f"session={token}"}, c["antwort"], 1)
    assert antwort.status_code == 403
    assert await _zaehler(fabrik, c["modell"]) == []


# ── Was bleibt, was geht ─────────────────────────────────────────────────────────

async def test_zaehler_ueberdauern_den_chat(test_client, auth_headers_student, chat, fabrik):
    c = await chat()
    await _put(test_client, auth_headers_student, c["antwort"], 1)
    assert (await test_client.delete(f"/conversations/{c['konv']}",
                                     headers=auth_headers_student)).status_code == 204
    async with fabrik() as db:
        assert await db.get(MessageRating, c["antwort"]) is None
    assert await _zaehler(fabrik, c["modell"]) == [("student", 1, 0)]


async def test_zuruecknehmen_nach_geloeschtem_assistenten(test_client, auth_headers_student,
                                                          chat, fabrik):
    """Der Assistent ist weg, seine Zähler mit ihm — Zurücknehmen darf nicht scheitern und
    nicht die Zeile „ohne Assistent“ ins Minus ziehen."""
    async with fabrik() as db:
        a = Assistant(name="T-Bewertung", system_prompt="P", model="chat-standard")
        db.add(a)
        await db.commit()
    c = await chat(assistant_id=a.id)
    await _put(test_client, auth_headers_student, c["antwort"], 1)
    async with fabrik() as db:
        await db.execute(sa.delete(Assistant).where(Assistant.id == a.id))
        await db.commit()
    antwort = await _put(test_client, auth_headers_student, c["antwort"], 0)
    assert antwort.status_code == 200, antwort.text
    assert await _zaehler(fabrik, c["modell"]) == []


# ── Nachrichtenliste ─────────────────────────────────────────────────────────────

async def test_liste_traegt_bewertung_und_bewertbar(test_client, auth_headers_student, chat):
    c = await chat()
    await _put(test_client, auth_headers_student, c["antwort"], -1)
    koerper = (await test_client.get(f"/conversations/{c['konv']}/messages",
                                     headers=auth_headers_student)).json()
    assert koerper["bewertbar"] is True
    assert {m["role"]: m["rating"] for m in koerper["messages"]} == {"user": None, "assistant": -1}


async def test_testchat_ist_nicht_bewertbar(test_client, auth_headers_student, chat):
    c = await chat(is_test=True)
    koerper = (await test_client.get(f"/conversations/{c['konv']}/messages",
                                     headers=auth_headers_student)).json()
    assert koerper["bewertbar"] is False
