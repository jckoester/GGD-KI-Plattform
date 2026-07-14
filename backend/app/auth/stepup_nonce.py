"""Einmalverwendung von Step-up-Token (Sicherheits-Audit #3 Teil C).

Verbraucht eine Token-`jti` atomar über die Tabelle `stepup_consumed`: der erste Einsatz
fügt ein, jeder weitere kollidiert am Primärschlüssel → abgelehnt (kein Replay im TTL-Fenster).
DB-basiert, damit die Sperre auch über mehrere uvicorn-Worker hält.
"""
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import StepupConsumed


async def consume_stepup_jti(db: AsyncSession, jti: str, expires_at: datetime) -> bool:
    """True, wenn die `jti` **erstmals** eingelöst wird; False bei Wiederverwendung (Replay)."""
    stmt = (
        pg_insert(StepupConsumed)
        .values(jti=jti, expires_at=expires_at)
        .on_conflict_do_nothing(index_elements=["jti"])
    )
    result = await db.execute(stmt)
    await db.commit()
    return (result.rowcount or 0) == 1
