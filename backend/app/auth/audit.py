from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import NormalizedIdentity
from app.db.models import PseudonymAudit


async def upsert_pseudonym_audit(
    db: AsyncSession, pseudonym: str, identity: NormalizedIdentity
) -> None:
    now = datetime.now(timezone.utc)
    grade_int = int(identity.grade) if identity.grade else None
    stmt = (
        pg_insert(PseudonymAudit)
        .values(
            pseudonym=pseudonym,
            role=identity.role,
            grade=grade_int,
            last_login_at=now,
        )
        .on_conflict_do_update(
            index_elements=["pseudonym"],
            set_={
                "role": identity.role,
                "grade": grade_int,
                "last_login_at": now,
            },
        )
    )
    await db.execute(stmt)
    await db.commit()
