"""Aufbewahrung des Audit-Logs (0.28, ADR-010 §2.3/§2.5).

Löscht je Klasse, was älter ist als ihre Frist:

| Klasse       | Frist      |
|--------------|------------|
| `auth`       | 180 Tage   |
| `admin`      | 2 Jahre    |
| `moderation` | 1 Jahr     |
| `system`     | 90 Tage    |
| `secret`     | unbefristet (wird nie gelöscht) |
| `access`     | steht in `conversation_access_audit`, nicht hier |

Der Trigger auf `audit_log` lässt das Löschen nur zu, wenn die Transaktion
`audit.aufraeumen = on` gesetzt hat — das tut dieser Lauf und sonst nur die Kontolöschung.
Das Ergebnis (Anzahl je Klasse) steht danach selbst im Audit-Log (`system.audit_log_cleaned`).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from time import perf_counter

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit
from app.db.models import AuditLog

logger = logging.getLogger(__name__)

#: ADR-010 §2.3 — `None` heißt unbefristet.
AUFBEWAHRUNG_TAGE: dict[str, int | None] = {
    "auth": 180,
    "admin": 730,
    "moderation": 365,
    "system": 90,
    "secret": None,
}


@dataclass
class AuditLoeschlauf:
    geloescht: dict[str, int] = field(default_factory=dict)
    duration_ms: int = 0


async def cleanup_audit_log(
    db: AsyncSession, *, dry_run: bool = False, now: datetime | None = None
) -> AuditLoeschlauf:
    start = perf_counter()
    jetzt = now or datetime.now(timezone.utc)
    lauf = AuditLoeschlauf()
    if not dry_run:
        await db.execute(select(func.set_config("audit.aufraeumen", "on", True)))
    for klasse, tage in AUFBEWAHRUNG_TAGE.items():
        if tage is None:
            continue
        grenze = jetzt - timedelta(days=tage)
        bedingung = (AuditLog.retention_class == klasse, AuditLog.occurred_at < grenze)
        if dry_run:
            anzahl = (await db.execute(select(func.count()).select_from(AuditLog).where(*bedingung))).scalar_one()
        else:
            anzahl = (await db.execute(delete(AuditLog).where(*bedingung))).rowcount or 0
        lauf.geloescht[klasse] = anzahl
    if not dry_run:
        await db.execute(select(func.set_config("audit.aufraeumen", "off", True)))
        # Erst nach dem Zurücksetzen: Der eigene Eintrag ist ein gewöhnliches Anhängen.
        await audit(db, "system", "audit_log_cleaned", daten={"geloescht": lauf.geloescht})
        await db.commit()
    lauf.duration_ms = int((perf_counter() - start) * 1000)
    return lauf
