"""Datenmodell für bekannte Probleme und Antwortbewertung (0.31, Päckchen T, Migration 0101).

Erfordert TEST_DATABASE_URL.
"""
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    Assistant, Conversation, Feedback, Message, MessageRating, RatingCount,
)

pytestmark = pytest.mark.asyncio

WOCHE = date(2026, 11, 2)


async def _antwort(db, assistant_id=None):
    konv = Conversation(pseudonym="t-modell", model_used="chat-standard")
    db.add(konv)
    await db.flush()
    antwort = Message(conversation_id=konv.id, role="assistant", content="Antwort",
                      model="chat-standard", assistant_id=assistant_id)
    db.add(antwort)
    await db.flush()
    return konv, antwort


async def _scheitert(db, objekt):
    """Einfügen in einem Sicherungspunkt — die Sitzung bleibt danach benutzbar."""
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(objekt)
            await db.flush()


def _meldung(**mehr):
    return Feedback(pseudonym="t-modell", role="student", category="bug",
                    content="Etwas geht nicht, ausführlich beschrieben.", app_version="0.31.0",
                    **mehr)


async def test_oeffentlich_nur_mit_titel_und_bekannter_zielgruppe(db_session):
    db = db_session
    db.add(_meldung(public_title="Formeln im PDF verrutschen", public_audience="teacher"))
    db.add(_meldung())
    await db.flush()
    await _scheitert(db, _meldung(public_audience="all"))
    await _scheitert(db, _meldung(public_title="Titel", public_audience="eltern"))


async def test_bewertung_nur_plus_minus_eins_und_bekannte_rolle(db_session):
    db = db_session
    _, antwort = await _antwort(db)
    await _scheitert(db, MessageRating(message_id=antwort.id, rating=0, rolle="student"))
    await _scheitert(db, MessageRating(message_id=antwort.id, rating=1, rolle="admin"))
    db.add(MessageRating(message_id=antwort.id, rating=-1, rolle="teacher"))
    await db.flush()


async def test_bewertung_geht_mit_dem_chat(db_session):
    db = db_session
    konv, antwort = await _antwort(db)
    db.add(MessageRating(message_id=antwort.id, rating=1, rolle="student"))
    await db.flush()
    await db.execute(sa.delete(Conversation).where(Conversation.id == konv.id))
    assert await db.get(MessageRating, antwort.id, populate_existing=True) is None


async def _zaehle(db, assistant_id, plus=0, minus=0):
    stmt = insert(RatingCount).values(woche=WOCHE, assistant_id=assistant_id,
                                      modell="chat-standard", rolle="student",
                                      plus=plus, minus=minus)
    await db.execute(stmt.on_conflict_do_update(
        constraint="uq_rating_counts_schluessel",
        set_={"plus": RatingCount.plus + plus, "minus": RatingCount.minus + minus},
    ))


async def test_zaehler_ohne_assistent_landen_in_einer_zeile(db_session):
    """NULLS NOT DISTINCT: Der Chat ohne Assistent zählt in eine Zeile, nicht in viele."""
    db = db_session
    await _zaehle(db, None, plus=1)
    await _zaehle(db, None, plus=1)
    await _zaehle(db, None, minus=1)
    zeilen = (await db.execute(sa.select(RatingCount).where(
        RatingCount.woche == WOCHE, RatingCount.assistant_id.is_(None)))).scalars().all()
    assert [(z.plus, z.minus) for z in zeilen] == [(2, 1)]


async def test_zaehler_ueberdauern_den_chat_und_folgen_dem_assistenten(db_session):
    db = db_session
    assistent = Assistant(name="T-Bewertet", system_prompt="P", model="chat-standard")
    db.add(assistent)
    await db.flush()
    konv, antwort = await _antwort(db, assistent.id)
    db.add(MessageRating(message_id=antwort.id, rating=1, rolle="student"))
    await _zaehle(db, assistent.id, plus=1)
    await db.flush()

    await db.execute(sa.delete(Conversation).where(Conversation.id == konv.id))
    stand = sa.select(RatingCount.plus).where(RatingCount.assistant_id == assistent.id)
    assert (await db.execute(stand)).scalar_one() == 1, "Der Chat ist weg, der Zähler bleibt"

    await db.execute(sa.delete(Assistant).where(Assistant.id == assistent.id))
    assert (await db.execute(stand)).scalar_one_or_none() is None


async def test_zaehler_werden_nicht_negativ(db_session):
    db = db_session
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await _zaehle(db, None, minus=-1)
