"""Die Güte der Kostenangabe — Spalte, Constraint und Statistik-Kennzahlen (AP1).

Bis Migration 0058 sah eine Teilsumme aus wie eine vollständige. Die
Admin-Statistik summierte sie und meldete stillschweigend zu wenig.
"""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Message
from tests.integration.conftest import TEACHER1_PSEUDO

pytestmark = pytest.mark.asyncio

JETZT = datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def zug(async_engine):
    """Eine Konversation mit drei Assistenten-Nachrichten verschiedener Güte."""
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        # Die Statistik verbindet über `pseudonym_audit` (dort hängen Rolle und Team).
        # Ohne diese Zeile fällt die Konversation aus dem Join — und der Test prüfte
        # dann eine Null, die nichts über die Kennzahl aussagt.
        await s.execute(text(
            "INSERT INTO pseudonym_audit (pseudonym, role) VALUES (:p, 'teacher') "
            "ON CONFLICT (pseudonym) DO NOTHING"
        ), {"p": TEACHER1_PSEUDO})
        conv = Conversation(id=uuid4(), pseudonym=TEACHER1_PSEUDO, model_used="gpt-4o")
        s.add(conv)
        await s.flush()
        for status, betrag in (
            ("vollstaendig", 0.010),
            ("unvollstaendig", 0.006),
            ("ausstehend", None),
        ):
            s.add(Message(
                conversation_id=conv.id, role="assistant", content="x",
                cost_usd=betrag, cost_status=status,
                created_at=JETZT - timedelta(minutes=5),
            ))
        await s.commit()
        yield conv.id

    async with factory() as s:
        await s.execute(delete(Message).where(Message.conversation_id == conv.id))
        await s.execute(delete(Conversation).where(Conversation.id == conv.id))
        await s.commit()


async def test_status_wird_gespeichert(db_session, zug):
    # Nur lesend — hier ist die transaktionale Sitzung unproblematisch.
    treffer = await db_session.execute(
        text("SELECT cost_status FROM messages WHERE conversation_id = :c "
             "ORDER BY cost_status"),
        {"c": str(zug)},
    )
    assert [r[0] for r in treffer.all()] == [
        "ausstehend", "unvollstaendig", "vollstaendig",
    ]


# ⚠️ Schreibende Prüfungen laufen in einer **eigenen**, sofort zurückgerollten
# Sitzung — nicht in `db_session`. Deren Transaktion bleibt bis zum Testende offen;
# eine dort gesetzte Zeilensperre trifft auf das Aufräumen der `zug`-Fixture, das
# dieselben Zeilen löschen will, und beide warten aufeinander. (Genau so gebaut und
# in einen Zwei-Minuten-Timeout gelaufen, 09.09.2026.)

async def test_unbekannter_status_wird_abgelehnt(async_engine, zug):
    """Der CHECK aus 0058 — ein Tippfehler soll beim Schreiben auffallen."""
    from sqlalchemy.exc import IntegrityError

    factory = async_sessionmaker(async_engine, class_=AsyncSession)
    async with factory() as s:
        with pytest.raises(IntegrityError):
            await s.execute(
                text("UPDATE messages SET cost_status = 'halbwegs' "
                     "WHERE conversation_id = :c"),
                {"c": str(zug)},
            )
        await s.rollback()


async def test_null_bleibt_erlaubt(async_engine, zug):
    """Bestandszeilen und User-Nachrichten tragen `NULL` = keine Aussage."""
    factory = async_sessionmaker(async_engine, class_=AsyncSession)
    async with factory() as s:
        await s.execute(
            text("UPDATE messages SET cost_status = NULL WHERE conversation_id = :c"),
            {"c": str(zug)},
        )
        await s.rollback()


async def test_statistik_weist_die_guete_aus(test_client, auth_headers, zug):
    von = (JETZT - timedelta(days=1)).date().isoformat()
    bis = (JETZT + timedelta(days=1)).date().isoformat()
    resp = await test_client.get(
        f"/admin/stats/spend?from_date={von}&to_date={bis}&granularity=day",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    daten = resp.json()
    # Die Zahlen sind untere Schranken: Die Test-Datenbank kann Zeilen anderer
    # Tests tragen. Geprüft wird, dass *diese* mitgezählt werden.
    assert daten["unvollstaendige_nachrichten"] >= 1
    assert daten["ausstehende_nachrichten"] >= 1
