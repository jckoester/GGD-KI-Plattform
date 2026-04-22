from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import NormalizedIdentity
from app.db.models import PseudonymAudit


def get_primary_role(roles: list[str]) -> str:
    """Gibt die budgetrelevante Hauptrolle zurück. Priorität: teacher > student."""
    if "teacher" in roles:
        return "teacher"
    if "student" in roles:
        return "student"
    return "teacher"


async def upsert_pseudonym_audit(
    db: AsyncSession, pseudonym: str, identity: NormalizedIdentity
) -> tuple[str | None, int | None]:
    # Altwerte vor dem Upsert lesen
    existing = await db.execute(
        select(PseudonymAudit.role, PseudonymAudit.grade).where(
            PseudonymAudit.pseudonym == pseudonym
        )
    )
    old_row = existing.fetchone()
    old_role = old_row.role if old_row else None
    old_grade = old_row.grade if old_row else None

    now = datetime.now(timezone.utc)
    grade_int = int(identity.grade) if identity.grade else None
    primary_role = get_primary_role(identity.roles)
    stmt = (
        pg_insert(PseudonymAudit)
        .values(
            pseudonym=pseudonym,
            role=primary_role,
            grade=grade_int,
            last_login_at=now,
        )
        .on_conflict_do_update(
            index_elements=["pseudonym"],
            set_={
                "role": primary_role,
                "grade": grade_int,
                "last_login_at": now,
            },
        )
    )
    await db.execute(stmt)
    await db.commit()
    return old_role, old_grade
