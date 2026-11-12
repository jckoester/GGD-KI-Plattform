"""Admin: Audit-Log lesen (0.28, Plan Schritt 6, F5 „einfach halten").

Nur lesend: Filter nach Kategorie, Ereignis, Akteur und Zeitraum, seitenweise, neueste zuerst.
Akteure erscheinen als Pseudonym — die Auflösung zu einer Person läuft weiterhin über die
4-Augen-Wege, nicht über diese Ansicht.

Die Bezeichnungen der Ereignisse stehen hier und nicht im Frontend, damit Positivliste
(`app/core/audit.py`) und Anzeige an einer Stelle zusammenpassen; ein Test prüft, dass jedes
Ereignis eine Bezeichnung hat.
"""
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.auth.jwt import JwtPayload
from app.core.audit import EREIGNISSE
from app.crons.audit_cleanup_service import AUFBEWAHRUNG_TAGE
from app.db.models import AuditLog
from app.db.session import get_db

router = APIRouter(prefix="/audit", tags=["admin-audit"])

BERLIN = ZoneInfo("Europe/Berlin")

KATEGORIEN: dict[str, str] = {
    "auth": "Anmeldung",
    "admin": "Verwaltung",
    "moderation": "Moderation",
    "system": "System",
}

BEZEICHNUNG: dict[str, str] = {
    "login_failed": "Anmeldung gescheitert",
    "stepup_denied": "Bestätigung der Anmeldung abgelehnt",
    "rate_limit_locked": "Drossel gesperrt",
    "feedback_blocked": "Rückmeldung abgewiesen (gesperrt)",
    "preview_entered": "Vorschau begonnen",
    "preview_exited": "Vorschau beendet",
    "assistant_approved": "Assistent freigegeben",
    "assistant_rejected": "Assistent abgelehnt",
    "assistant_activated": "Assistent aktiviert",
    "assistant_deactivated": "Assistent deaktiviert",
    "assistant_deleted": "Assistent gelöscht",
    "model_access_changed": "Modell-Freischaltung geändert",
    "budget_changed": "Wochenbetrag geändert",
    "budget_granted": "Zuschlag gebucht",
    "guardrail_changed": "Guardrail geändert",
    "site_text_changed": "Site-Text geändert",
    "holidays_changed": "Ferienkalender geändert",
    "user_sessions_revoked": "Sitzungen beendet",
    "feedback_status_changed": "Feedback-Status geändert",
    "feedback_public_changed": "Bekanntes Problem gezeigt oder zurückgenommen",
    "crisis_flag_created": "Krisen-Flag angelegt",
    "crisis_flag_resolved": "Krisen-Flag erledigt",
    "accounts_cleaned": "Konten gelöscht (Löschlauf)",
    "conversations_cleaned": "Chats gelöscht (Löschlauf)",
    "node_lifecycle_run": "Lebenszyklus der Bibliothek",
    "audit_log_cleaned": "Audit-Log aufgeräumt",
}

MAX_PRO_SEITE = 200


class Ereignisart(BaseModel):
    name: str
    bezeichnung: str


class Kategorie(BaseModel):
    name: str
    bezeichnung: str
    aufbewahrung_tage: Optional[int]
    ereignisse: list[Ereignisart]


class KatalogResponse(BaseModel):
    kategorien: list[Kategorie]


class Eintrag(BaseModel):
    id: int
    occurred_at: datetime
    category: str
    event_type: str
    bezeichnung: str
    actor_pseudonym: Optional[str]
    actor_role: Optional[str]
    target_type: Optional[str]
    target_id: Optional[str]
    payload: dict


class AuditResponse(BaseModel):
    eintraege: list[Eintrag]
    gesamt: int
    seite: int
    pro_seite: int


@router.get("/katalog", response_model=KatalogResponse)
async def katalog(_: JwtPayload = Depends(require_role("admin"))) -> KatalogResponse:
    """Kategorien und Ereignisse für die Filter — nur, was überhaupt vorkommen kann."""
    return KatalogResponse(kategorien=[
        Kategorie(
            name=k,
            bezeichnung=b,
            aufbewahrung_tage=AUFBEWAHRUNG_TAGE.get(k),
            ereignisse=[Ereignisart(name=e, bezeichnung=BEZEICHNUNG.get(e, e))
                        for e in sorted(EREIGNISSE[k], key=lambda e: BEZEICHNUNG.get(e, e))],
        )
        for k, b in KATEGORIEN.items()
    ])


def _tagesbeginn(tag: date) -> datetime:
    return datetime.combine(tag, time.min, tzinfo=BERLIN)


@router.get("", response_model=AuditResponse)
async def list_audit(
    kategorie: Optional[str] = Query(default=None),
    ereignis: Optional[str] = Query(default=None),
    akteur: Optional[str] = Query(default=None, description="Pseudonym oder dessen Anfang"),
    von: Optional[date] = Query(default=None, description="Erster Tag (Ortszeit), einschließlich"),
    bis: Optional[date] = Query(default=None, description="Letzter Tag (Ortszeit), einschließlich"),
    seite: int = Query(default=1, ge=1),
    pro_seite: int = Query(default=50, ge=1, le=MAX_PRO_SEITE),
    _: JwtPayload = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> AuditResponse:
    if kategorie is not None and kategorie not in EREIGNISSE:
        raise HTTPException(status_code=422, detail="Unbekannte Kategorie.")
    if von and bis and von > bis:
        raise HTTPException(status_code=422, detail="Der Zeitraum endet vor seinem Beginn.")

    bedingungen = []
    if kategorie:
        bedingungen.append(AuditLog.category == kategorie)
    if ereignis:
        bedingungen.append(AuditLog.event_type == ereignis)
    if akteur and akteur.strip():
        bedingungen.append(AuditLog.actor_pseudonym.startswith(akteur.strip(), autoescape=True))
    if von:
        bedingungen.append(AuditLog.occurred_at >= _tagesbeginn(von))
    if bis:
        bedingungen.append(AuditLog.occurred_at < _tagesbeginn(bis + timedelta(days=1)))

    gesamt = (await db.execute(
        select(func.count()).select_from(AuditLog).where(*bedingungen)
    )).scalar_one()
    zeilen = (await db.execute(
        select(AuditLog).where(*bedingungen)
        .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
        .offset((seite - 1) * pro_seite).limit(pro_seite)
    )).scalars().all()

    return AuditResponse(
        eintraege=[Eintrag(
            id=z.id, occurred_at=z.occurred_at, category=z.category, event_type=z.event_type,
            bezeichnung=BEZEICHNUNG.get(z.event_type, z.event_type),
            actor_pseudonym=z.actor_pseudonym, actor_role=z.actor_role,
            target_type=z.target_type, target_id=z.target_id, payload=z.payload or {},
        ) for z in zeilen],
        gesamt=gesamt,
        seite=seite,
        pro_seite=pro_seite,
    )
