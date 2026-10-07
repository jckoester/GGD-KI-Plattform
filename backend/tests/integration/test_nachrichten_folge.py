"""Die Reihenfolge eines Gesprächs (07.10.2026).

Frage und Antwort eines Zuges tragen denselben Zeitstempel — `now()` ist der Beginn der
Transaktion, in der `_persist` beide schreibt. Sortiert wurde nur nach `created_at`, und
bei Gleichstand lieferte die Datenbank die Folge ihres Abfrageplans: Seit der Plan des
Ladewegs auf einen Hash Right Join kippte, stand jede Antwort über ihrer Frage.

Der Fall hier ist so gebaut, dass **jeder** Plan ohne zweites Sortierkriterium falsch
sortiert: Die Antwort liegt physisch vor der Frage (Scan-Reihenfolge) und hat einen
Assistenten, die Frage nicht (Hash Right Join gibt sie zuletzt aus).
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Message
from tests.integration.conftest import TEACHER1_PSEUDO

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def gespraech(async_engine, seed_test_assistant):
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    zug1 = datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)
    zug2 = zug1 + timedelta(minutes=2)
    async with factory() as s:
        konv = Conversation(id=uuid4(), pseudonym=TEACHER1_PSEUDO, model_used="model-x")
        s.add(konv)
        await s.flush()
        # Je Zug: erst die Antwort, dann die Frage — einzeln geschrieben, damit die
        # physische Lage feststeht.
        for zeitpunkt, nr in ((zug1, 1), (zug2, 2)):
            for rolle in ("assistant", "user"):
                s.add(Message(
                    conversation_id=konv.id, role=rolle, created_at=zeitpunkt,
                    content=f"{'Antwort' if rolle == 'assistant' else 'Frage'} {nr}",
                    assistant_id=seed_test_assistant if rolle == "assistant" else None,
                ))
                await s.flush()
        await s.commit()
        konv_id = konv.id
    yield konv_id
    async with factory() as s:
        await s.execute(delete(Conversation).where(Conversation.id == konv_id))
        await s.commit()


ERWARTET = ["Frage 1", "Antwort 1", "Frage 2", "Antwort 2"]


async def test_neuladen_zeigt_die_frage_vor_der_antwort(test_client, auth_headers, gespraech):
    resp = await test_client.get(f"/conversations/{gespraech}/messages", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert [m["content"] for m in resp.json()["messages"]] == ERWARTET


async def test_feedback_schnappschuss_in_derselben_folge(db_session, gespraech):
    from app.feedback.snapshot import lade

    schnappschuss = await lade(db_session, gespraech, TEACHER1_PSEUDO)
    assert [m["content"] for m in schnappschuss["messages"]] == ERWARTET
