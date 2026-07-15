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


def roles_were_removed(old_roles: list[str] | None, new_roles: list[str]) -> bool:
    """True, wenn seit dem letzten Login mindestens eine Rolle ENTZOGEN wurde (Audit #11 „E").

    Ohne Baseline (``old_roles is None``, erster Login nach dem Rollout) wird nicht revoziert.
    Reine Hinzufügung (Hochstufung) löst ebenfalls keine Revocation aus — Alt-Sessions sind
    dann nur unterprivilegiert, kein Sicherheitsproblem.
    """
    if old_roles is None:
        return False
    return bool(set(old_roles) - set(new_roles))


async def upsert_pseudonym_audit(
    db: AsyncSession, pseudonym: str, identity: NormalizedIdentity
) -> tuple[str | None, int | None]:
    # Altwerte vor dem Upsert lesen (inkl. vollem Rollensatz für die Schrumpfungs-Erkennung).
    existing = await db.execute(
        select(PseudonymAudit.role, PseudonymAudit.grade, PseudonymAudit.roles).where(
            PseudonymAudit.pseudonym == pseudonym
        )
    )
    old_row = existing.fetchone()
    old_role = old_row.role if old_row else None
    old_grade = old_row.grade if old_row else None
    old_roles = old_row.roles if old_row else None

    now = datetime.now(timezone.utc)
    grade_int = int(identity.grade) if identity.grade else None
    primary_role = get_primary_role(identity.roles)
    new_roles = list(identity.roles)

    # Automatische Session-Revocation (Sicherheits-Audit #11, „E"): Wurde dem Nutzer seit dem
    # letzten Login mindestens eine Rolle ENTZOGEN (typisch: additives admin/review weg), werden
    # alle vor jetzt ausgestellten Token ungültig (`revoked_all_before`). So verlieren parallele
    # Alt-Sessions (anderes Gerät) mit noch-erhöhter Rolle sofort ihre Rechte. Das gleich danach
    # ausgestellte neue Token überlebt: `revoked_all_before` wird auf die volle Sekunde abgerundet,
    # das neue `iat` (Sekunden-genau) ist ≥ dieser Grenze → `iat < revoked_all_before` ist False.
    revoked_all_before = None
    if roles_were_removed(old_roles, new_roles):
        revoked_all_before = datetime.fromtimestamp(int(now.timestamp()), tz=timezone.utc)

    values = {
        "pseudonym": pseudonym,
        "role": primary_role,
        "roles": new_roles,
        "grade": grade_int,
        "last_login_at": now,
    }
    set_ = {
        "role": primary_role,
        "roles": new_roles,
        "grade": grade_int,
        "last_login_at": now,
    }
    if revoked_all_before is not None:
        values["revoked_all_before"] = revoked_all_before
        set_["revoked_all_before"] = revoked_all_before

    stmt = pg_insert(PseudonymAudit).values(**values).on_conflict_do_update(
        index_elements=["pseudonym"],
        set_=set_,
    )
    await db.execute(stmt)
    await db.commit()
    return old_role, old_grade
