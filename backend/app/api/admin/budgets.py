import asyncio
import logging
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_any_role
from app.auth.jwt import JwtPayload
from app.budget.exchange import get_current_rate
from app.budget.tiers import invalidate_budget_tiers_cache, _load_budget_tiers
from app.config import settings
from app.db.session import get_db
from app.litellm.client import LiteLLMClient
from app.litellm.teams import STUDENT_TEAM_PREFIX, TEACHER_TEAM_ID, VALID_GRADES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/budgets", tags=["admin-budgets"])


# Pydantic-Modelle
class GradeInfo(BaseModel):
    key: str  # "jahrgang-5"..."jahrgang-12" | "lehrkraefte"
    label: str  # "Jahrgang 5"..."Jahrgang 12" | "Lehrkräfte"
    grade: Optional[int]  # None für Lehrkräfte
    max_budget_eur: float
    budget_duration: str  # "1mo"
    user_count: int  # Nutzer in pseudonym_audit


class BudgetGradesResponse(BaseModel):
    grades: list[GradeInfo]  # aufsteigend nach grade, Lehrkräfte am Ende
    eur_usd_rate: float


class GradeUpdate(BaseModel):
    key: str
    max_budget_eur: float


class BudgetGradesUpdateRequest(BaseModel):
    grades: list[GradeUpdate]


class BudgetGradesUpdateResult(BaseModel):
    ok: bool
    updated_users: int


@router.get("/grades", response_model=BudgetGradesResponse)
async def get_budget_grades(
    _: JwtPayload = Depends(require_any_role(["budget", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> BudgetGradesResponse:
    """
    Gibt die Budget-Einstellungen pro Jahrgang/Rolle zurück.
    Enthält auch die Nutzerzahlen aus der pseudonym_audit-Tabelle.
    """
    # YAML laden
    config = _load_budget_tiers()

    # Nutzeranzahl aus pseudonym_audit
    result = await db.execute(
        text("SELECT role, grade, COUNT(*)::int FROM pseudonym_audit GROUP BY role, grade")
    )
    counts = {(row[0], row[1]): row[2] for row in result.fetchall()}

    # GradeInfo-Liste bauen
    rows = []
    for g in sorted(VALID_GRADES):
        grade_cfg = config.get("grades", {}).get(g, {})
        rows.append(GradeInfo(
            key=f"{STUDENT_TEAM_PREFIX}{g}",
            label=f"Jahrgang {g}",
            grade=g,
            max_budget_eur=grade_cfg.get("max_budget_eur", 0.0),
            budget_duration=grade_cfg.get("budget_duration", "1mo"),
            user_count=counts.get(("student", g), 0),
        ))

    teacher_cfg = config.get("roles", {}).get("teacher", {})
    teacher_count = sum(v for (role, _), v in counts.items() if role == "teacher")
    rows.append(GradeInfo(
        key=TEACHER_TEAM_ID,
        label="Lehrkräfte",
        grade=None,
        max_budget_eur=teacher_cfg.get("max_budget_eur", 0.0),
        budget_duration=teacher_cfg.get("budget_duration", "1mo"),
        user_count=teacher_count,
    ))

    # EUR/USD-Kurs
    eur_usd_rate = await get_current_rate(db)

    return BudgetGradesResponse(grades=rows, eur_usd_rate=eur_usd_rate)


@router.post("/grades", response_model=BudgetGradesUpdateResult)
async def update_budget_grades(
    body: BudgetGradesUpdateRequest,
    _: JwtPayload = Depends(require_any_role(["budget", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> BudgetGradesUpdateResult:
    """
    Aktualisiert die budgets pro Jahrgang/Rolle.
    
    - Validiert, dass alle max_budget_eur > 0 sind
    - Validiert, dass alle Keys bekannt sind (jahrgang-5...jahrgang-12 oder lehrkraefte)
    - Schreibt die YAML atomar (tmp + replace)
    - Invalidiert den Cache
    - Aktualisiert alle betroffenen LiteLLM-User-Budgets parallel
    """
    # 1. Validieren: max_budget_eur > 0 für alle Einträge
    for update in body.grades:
        if update.max_budget_eur <= 0:
            raise HTTPException(
                status_code=422,
                detail=f"max_budget_eur muss > 0 sein, erhalten: {update.max_budget_eur} für {update.key}"
            )

    # 2. Bekannte Keys bestimmen
    valid_keys = {f"{STUDENT_TEAM_PREFIX}{g}" for g in VALID_GRADES} | {TEACHER_TEAM_ID}
    unknown = {u.key for u in body.grades} - valid_keys
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unbekannte Keys: {sorted(unknown)}"
        )

    # 3. YAML lesen (aktueller Stand)
    config_path = Path(settings.budget_tiers_path)
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # 4. YAML-Struktur aktualisieren
    updates = {u.key: u.max_budget_eur for u in body.grades}
    for key, eur in updates.items():
        if key == TEACHER_TEAM_ID:
            raw.setdefault("roles", {}).setdefault("teacher", {})["max_budget_eur"] = eur
        else:
            grade = int(key[len(STUDENT_TEAM_PREFIX):])
            raw.setdefault("grades", {}).setdefault(grade, {})["max_budget_eur"] = eur

    # 5. Atomar schreiben
    tmp = config_path.with_suffix(".yaml.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.dump(raw, f, allow_unicode=True, default_flow_style=False)
    tmp.replace(config_path)

    # 6. Cache invalidieren
    invalidate_budget_tiers_cache()

    # 7. Betroffene Nutzer ermitteln (geänderte Keys)
    changed_keys = {u.key for u in body.grades}
    tasks = []  # [(pseudonym, new_eur, duration)]
    
    for update in body.grades:
        if update.key == TEACHER_TEAM_ID:
            result = await db.execute(
                text("SELECT pseudonym FROM pseudonym_audit WHERE role = 'teacher'")
            )
            duration = raw["roles"]["teacher"].get("budget_duration", "1mo")
        else:
            grade = int(update.key[len(STUDENT_TEAM_PREFIX):])
            result = await db.execute(
                text("SELECT pseudonym FROM pseudonym_audit WHERE role = 'student' AND grade = :g"),
                {"g": grade}
            )
            duration = raw["grades"].get(grade, {}).get("budget_duration", "1mo")
        
        for row in result.fetchall():
            tasks.append((row[0], update.max_budget_eur, duration))

    # 8. LiteLLM-Budgets parallel aktualisieren
    eur_usd = await get_current_rate(db)
    sem = asyncio.Semaphore(10)
    success = 0

    async def update_one(pseudonym: str, eur: float, duration: str) -> None:
        nonlocal success
        async with sem:
            usd = round(eur * eur_usd, 2)
            client = LiteLLMClient()
            try:
                await client.update_user_budget(pseudonym, usd, duration)
                success += 1
                logger.info("Budget-Update erfolgreich für %s: %.2f USD", pseudonym, usd)
            except Exception:
                logger.exception("Budget-Update fehlgeschlagen für %s", pseudonym)
            finally:
                await client.close()

    try:
        await asyncio.gather(*[update_one(p, e, d) for p, e, d in tasks])
    except Exception:
        logger.exception("Fehler beim parallelen Budget-Update")

    logger.info("Budget-Update abgeschlossen: %d/%d Nutzer erfolgreich aktualisiert", success, len(tasks))

    return BudgetGradesUpdateResult(ok=True, updated_users=success)
