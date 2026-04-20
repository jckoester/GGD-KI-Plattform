from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession


async def get_preferences(db: AsyncSession, pseudonym: str) -> dict:
    result = await db.execute(
        text("SELECT preferences FROM user_preferences WHERE pseudonym = :pseudonym"),
        {"pseudonym": pseudonym},
    )
    row = result.fetchone()
    return row[0] if row else {}


async def patch_preferences(db: AsyncSession, pseudonym: str, updates: dict) -> dict:
    result = await db.execute(
        text("SELECT preferences FROM user_preferences WHERE pseudonym = :pseudonym"),
        {"pseudonym": pseudonym},
    )
    row = result.fetchone()
    current = row[0] if row else {}
    merged = {**current, **updates}
    await db.execute(
        text("""
            INSERT INTO user_preferences (pseudonym, preferences)
            VALUES (:pseudonym, :preferences)
            ON CONFLICT (pseudonym) DO UPDATE SET preferences = EXCLUDED.preferences
        """).bindparams(bindparam("preferences", type_=JSONB())),
        {"pseudonym": pseudonym, "preferences": merged},
    )
    await db.commit()
    return merged
