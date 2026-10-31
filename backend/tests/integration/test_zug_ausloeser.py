"""Zug-Auslöser: Ablage und Abfrage früherer Treffer (0.26, Rückfall Schritt 10, Migration 0094)."""
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, ZugAusloeser
from app.pedagogy import druck as D

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def sitzungen(async_engine):
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    yield fabrik
    async with fabrik() as db:
        await db.execute(sa.delete(Conversation).where(Conversation.pseudonym == "zug-ausloeser-probe"))
        await db.commit()


async def test_ablage_und_fruehere_treffer(sitzungen):
    async with sitzungen() as db:
        conv = Conversation(id=uuid4(), pseudonym="zug-ausloeser-probe", model_used="chat-komplex")
        db.add(conv)
        await db.commit()
    druck = D.Befund(D.Erkennung(True, "korpus", 0.2, 0.4), 1, False)
    kein = D.Befund(D.Erkennung(False), 0, False)
    lehrkraft = D.Befund(D.Erkennung(True, "regex"), 1, True)
    await D.speichere(conv.id, 1, {"druck": druck, "lehrkraft": None}, sitzungen=sitzungen)
    await D.speichere(conv.id, 2, {"druck": kein, "lehrkraft": lehrkraft}, sitzungen=sitzungen)
    async with sitzungen() as db:
        zeilen = (await db.execute(sa.select(ZugAusloeser.art, ZugAusloeser.nutzer_nachricht, ZugAusloeser.anweisung)
                                   .where(ZugAusloeser.conversation_id == conv.id)
                                   .order_by(ZugAusloeser.nutzer_nachricht))).all()
        assert [tuple(z) for z in zeilen] == [("druck", 1, False), ("lehrkraft", 2, True)]   # ohne Treffer keine Zeile
        assert await D.fruehere_druck_treffer(db, conv.id, 3) == [True, False, False]
        assert await D.fruehere_druck_treffer(db, None, 2) == [False, False]


async def test_speichern_wirft_nie(sitzungen):
    # Unbekanntes Gespräch: Fremdschlüssel verletzt — geloggt, nicht geworfen.
    await D.speichere(uuid4(), 1, {"druck": D.Befund(D.Erkennung(True, "regex"), 1, False)}, sitzungen=sitzungen)
