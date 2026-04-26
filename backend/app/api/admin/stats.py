from datetime import date, datetime, timedelta
from typing import Literal, Tuple
from zoneinfo import ZoneInfo
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_any_role
from app.auth.jwt import JwtPayload
from app.db.models import ExchangeRate
from app.db.session import get_db
from app.litellm.teams import TEACHER_TEAM_ID, STUDENT_TEAM_PREFIX

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stats", tags=["admin-stats"])

BERLIN = ZoneInfo("Europe/Berlin")
UTC = ZoneInfo("UTC")


class HeatmapCell(BaseModel):
    dow: int
    hour: int
    count: int


class HeatmapResponse(BaseModel):
    week_start: date
    week_end: date
    cells: list[HeatmapCell]
    team_id: str | None


class SpendEntry(BaseModel):
    period: str
    usd: float
    eur: float


class SpendResponse(BaseModel):
    entries: list[SpendEntry]
    total_usd: float
    total_eur: float
    eur_usd_rate: float
    team_id: str | None


def _team_conditions(team_id: str | None) -> list[tuple[str, str | int]]:
    if team_id is None:
        return []
    if team_id == TEACHER_TEAM_ID:
        return [("role", "teacher")]
    if team_id.startswith(STUDENT_TEAM_PREFIX):
        try:
            grade = int(team_id[len(STUDENT_TEAM_PREFIX):])
            return [("role", "student"), ("grade", grade)]
        except (ValueError, IndexError):
            return []
    return []


def _build_team_where(
    team_id: str | None,
    params: dict,
    prefix: str = "",
) -> Tuple[str, dict]:
    conditions = _team_conditions(team_id)
    if not conditions:
        return "", {}

    where_parts = []
    additional_params = {}
    for col, val in conditions:
        param_name = f"{prefix}pa_{col}"
        where_parts.append(f"pa.{col} = :{param_name}")
        additional_params[param_name] = val

    return " AND " + " AND ".join(where_parts), additional_params


def _format_period(period_dt: datetime, granularity: Literal["month", "week", "day"]) -> str:
    if granularity == "month":
        return period_dt.strftime("%Y-%m")
    elif granularity == "week":
        iso = period_dt.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    else:
        return period_dt.strftime("%Y-%m-%d")


@router.get("/heatmap", response_model=HeatmapResponse)
async def get_heatmap(
    week_offset: int = 0,
    team_id: str | None = None,
    _: JwtPayload = Depends(require_any_role(["statistics", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> HeatmapResponse:
    today = datetime.now(BERLIN).date()
    monday = today - timedelta(days=today.weekday())
    week_start = monday + timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=6)

    from_utc = datetime(week_start.year, week_start.month, week_start.day,
                        tzinfo=BERLIN).astimezone(UTC)
    to_utc = datetime(week_end.year, week_end.month, week_end.day,
                      23, 59, 59, tzinfo=BERLIN).astimezone(UTC)

    params: dict = {"from_utc": from_utc, "to_utc": to_utc}
    team_where, team_params = _build_team_where(team_id, params)
    params.update(team_params)

    sql = f"""
        SELECT
            (EXTRACT(DOW FROM m.created_at AT TIME ZONE 'Europe/Berlin')::int + 6) % 7 AS dow,
            EXTRACT(HOUR FROM m.created_at AT TIME ZONE 'Europe/Berlin')::int AS hour,
            COUNT(*)::int AS count
        FROM messages m
        JOIN conversations c ON m.conversation_id = c.id
        JOIN pseudonym_audit pa ON c.pseudonym = pa.pseudonym
        WHERE m.role = 'user'
          AND m.created_at >= :from_utc
          AND m.created_at <= :to_utc
          {team_where}
        GROUP BY dow, hour
        ORDER BY dow, hour
    """

    try:
        from sqlalchemy import text
        result = await db.execute(text(sql), params)
        rows = result.fetchall()
    except Exception:
        logger.exception("Fehler beim Laden der Heatmap-Daten")
        raise HTTPException(status_code=500, detail="Interner Serverfehler")

    cells = [HeatmapCell(dow=row[0], hour=row[1], count=row[2]) for row in rows]
    return HeatmapResponse(
        week_start=week_start,
        week_end=week_end,
        cells=cells,
        team_id=team_id,
    )


@router.get("/spend", response_model=SpendResponse)
async def get_spend(
    from_date: date | None = None,
    to_date: date | None = None,
    team_id: str | None = None,
    granularity: Literal["month", "week", "day"] = "month",
    _: JwtPayload = Depends(require_any_role(["statistics", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> SpendResponse:
    today = datetime.now(BERLIN).date()
    if from_date is None:
        from_date = today - timedelta(days=90)
    if to_date is None:
        to_date = today

    from_utc = datetime(from_date.year, from_date.month, from_date.day,
                        tzinfo=BERLIN).astimezone(UTC)
    to_utc = datetime(to_date.year, to_date.month, to_date.day,
                      23, 59, 59, tzinfo=BERLIN).astimezone(UTC)

    rate_result = await db.execute(
        select(ExchangeRate.eur_usd_rate)
        .order_by(ExchangeRate.effective_from.desc())
        .limit(1)
    )
    rate: float = float(rate_result.scalar_one_or_none() or 1.0)

    params: dict = {"from_utc": from_utc, "to_utc": to_utc}
    team_where, team_params = _build_team_where(team_id, params)
    params.update(team_params)

    sql = f"""
        SELECT
            DATE_TRUNC('{granularity}', m.created_at AT TIME ZONE 'Europe/Berlin') AS period,
            SUM(m.cost_usd)::float AS total_usd
        FROM messages m
        JOIN conversations c ON m.conversation_id = c.id
        JOIN pseudonym_audit pa ON c.pseudonym = pa.pseudonym
        WHERE m.role = 'assistant'
          AND m.cost_usd IS NOT NULL
          AND m.created_at >= :from_utc
          AND m.created_at <= :to_utc
          {team_where}
        GROUP BY period
        ORDER BY period
    """

    try:
        from sqlalchemy import text
        result = await db.execute(text(sql), params)
        rows = result.fetchall()
    except Exception:
        logger.exception("Fehler beim Laden der Spend-Daten")
        raise HTTPException(status_code=500, detail="Interner Serverfehler")

    entries = []
    for row in rows:
        period_dt = row[0]
        total_usd = float(row[1] or 0.0)
        period_str = _format_period(period_dt, granularity)
        total_eur = total_usd / rate
        entries.append(SpendEntry(
            period=period_str,
            usd=round(total_usd, 6),
            eur=round(total_eur, 6),
        ))

    total_usd = sum(e.usd for e in entries)
    total_eur = sum(e.eur for e in entries)
    return SpendResponse(
        entries=entries,
        total_usd=round(total_usd, 6),
        total_eur=round(total_eur, 6),
        eur_usd_rate=rate,
        team_id=team_id,
    )
