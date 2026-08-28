import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.auth.jwt import JwtPayload
from app.config import settings
from app.db.models import SiteConfig
from app.db.session import get_db
from app.litellm.client import LiteLLMClient

logger = logging.getLogger(__name__)

# Repo-Root: backend/app/api/admin/guardrail.py → parents[4]
_REPO_ROOT = Path(__file__).resolve().parents[4]


def _alter_in_stunden(zeitstempel: str | None) -> float | None:
    """Alter des Berichts in Stunden. None, wenn der Zeitstempel unbrauchbar ist."""
    if not zeitstempel:
        return None
    try:
        gesetzt = datetime.fromisoformat(zeitstempel)
    except (TypeError, ValueError):
        return None
    if gesetzt.tzinfo is None:
        gesetzt = gesetzt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - gesetzt).total_seconds() / 3600


def _resolve(path_str: str) -> Path:
    """Absoluter Pfad bleibt; relativer wird am Repo-Root verankert (cwd-unabhängig).

    Ohne das zeigt `data/guardrail_health.json` je nach Startverzeichnis woandershin —
    das Backend läuft aus `backend/`, der Proxy aus `infra/`. Beide müssen aber dieselbe
    Datei meinen, sonst meldet der Endpunkt „kein Bericht", obwohl es einen gibt.
    """
    p = Path(path_str)
    return p if p.is_absolute() else _REPO_ROOT / p


router = APIRouter(prefix="/guardrail", tags=["admin-guardrail"])

_litellm = LiteLLMClient()
_GUARDRAIL_KEY = "guardrail_prompt"


# ---------- Pydantic-Schemas ----------

class GuardrailPromptResponse(BaseModel):
    prompt: str | None
    updated_at: datetime | None
    updated_by: str | None


class GuardrailPromptUpdate(BaseModel):
    prompt: str | None = Field(default=None, max_length=10_000)


class LiteLLMGuardrailItem(BaseModel):
    name: str
    mode: str | None = None


class LiteLLMGuardrailsResponse(BaseModel):
    guardrails: list[LiteLLMGuardrailItem]
    available: bool  # False wenn LiteLLM nicht erreichbar war


class GuardrailHealthResponse(BaseModel):
    """Betriebszustand des Jugendschutz-Klassifikators.

    `available=False` heißt: kein Zustandsbericht vorhanden — nicht „alles in Ordnung".
    """

    available: bool
    hinweis: str | None = None
    healthy: bool | None = None
    # True = Bericht vorhanden, aber zu alt. Eigenes Feld, damit ein Monitoring den
    # stehengebliebenen Proxy von echten Klassifikator-Ausfällen unterscheiden kann.
    stale: bool = False
    classifier_model: str | None = None
    fallback_model: str | None = None
    checked_at: str | None = None
    total: int = 0
    failure_rate: float = 0.0
    # primary_ok · retry_ok · fallback_ok · failed_open · failed_closed · blocked
    counters: dict[str, int] = Field(default_factory=dict)


# ---------- Endpunkte ----------

@router.get("/prompt", response_model=GuardrailPromptResponse)
async def get_guardrail_prompt(
    db: AsyncSession = Depends(get_db),
    _: JwtPayload = Depends(require_role("admin")),
) -> GuardrailPromptResponse:
    result = await db.execute(
        select(SiteConfig).where(SiteConfig.key == _GUARDRAIL_KEY)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return GuardrailPromptResponse(prompt=None, updated_at=None, updated_by=None)
    return GuardrailPromptResponse(
        prompt=row.value,
        updated_at=row.updated_at,
        updated_by=row.updated_by,
    )


@router.put("/prompt", response_model=GuardrailPromptResponse)
async def update_guardrail_prompt(
    body: GuardrailPromptUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: JwtPayload = Depends(require_role("admin")),
) -> GuardrailPromptResponse:
    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(SiteConfig)
        .values(
            key=_GUARDRAIL_KEY,
            value=body.prompt,
            updated_at=now,
            updated_by=current_user.sub,
        )
        .on_conflict_do_update(
            index_elements=["key"],
            set_={
                "value": body.prompt,
                "updated_at": now,
                "updated_by": current_user.sub,
            },
        )
    )
    await db.execute(stmt)
    await db.commit()

    # Chat-Router-Cache invalidieren
    import app.chat.router as chat_router
    chat_router._guardrail_prompt_cache = None

    result = await db.execute(
        select(SiteConfig).where(SiteConfig.key == _GUARDRAIL_KEY)
    )
    row = result.scalar_one()
    return GuardrailPromptResponse(
        prompt=row.value,
        updated_at=row.updated_at,
        updated_by=row.updated_by,
    )


@router.get("/litellm", response_model=LiteLLMGuardrailsResponse)
async def get_litellm_guardrails(
    _: JwtPayload = Depends(require_role("admin")),
) -> LiteLLMGuardrailsResponse:
    raw = await _litellm.list_guardrails()
    items = [LiteLLMGuardrailItem(name=g["name"], mode=g.get("mode")) for g in raw]
    return LiteLLMGuardrailsResponse(guardrails=items, available=True)


@router.get("/health", response_model=GuardrailHealthResponse)
async def get_guardrail_health(
    _: JwtPayload = Depends(require_role("admin")),
) -> GuardrailHealthResponse:
    """Betriebszustand des Jugendschutz-Klassifikators.

    Der Guardrail läuft im LiteLLM-Proxy, nicht hier — er legt seinen Zählerstand als
    JSON ab (`health_file` in der LiteLLM-Config), das Backend reicht ihn durch. Ein
    Monitoring kann diesen Endpunkt abfragen; **Benachrichtigungen verschickt die
    Plattform selbst nicht.**

    Fehlt die Datei, ist das kein Fehler, sondern eine Aussage: Entweder ist `health_file`
    nicht konfiguriert, oder seit dem Proxy-Start wurde noch keine Antwort geprüft.
    """
    pfad = _resolve(settings.guardrail_health_file)
    if not pfad.is_file():
        return GuardrailHealthResponse(
            available=False,
            hinweis=(
                f"Kein Zustandsbericht unter '{pfad}'. Entweder ist `health_file` in der "
                "LiteLLM-Config nicht gesetzt, oder der Proxy hat seit dem Start noch "
                "keine Antwort geprüft."
            ),
        )
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Guardrail-Zustandsbericht unlesbar (%s): %s", pfad, exc)
        return GuardrailHealthResponse(
            available=False, hinweis=f"Zustandsbericht unter '{pfad}' ist unlesbar."
        )

    zaehler = daten.get("counters") or {}
    healthy = bool(daten.get("healthy", True))

    # Ein eingefrorener Bericht ist der gefährlichste Zustand: Stoppt der Proxy — oder
    # bricht die gemeinsame Ablage weg —, bleibt die Datei mit `healthy: true` liegen und
    # ein Monitoring meldete unbegrenzt „alles in Ordnung", obwohl seit Tagen nichts
    # geprüft wird. Alter deshalb immer mitbewerten.
    veraltet = False
    hinweis = None
    alter = _alter_in_stunden(daten.get("checked_at"))
    if alter is None:
        veraltet, healthy = True, False
        hinweis = "Bericht ohne verwertbaren Zeitstempel — Alter nicht beurteilbar."
    elif alter > settings.guardrail_health_max_age_h:
        veraltet, healthy = True, False
        hinweis = (
            f"Bericht ist {alter:.1f} Stunden alt (Grenze: "
            f"{settings.guardrail_health_max_age_h}). Läuft der LiteLLM-Proxy noch, und "
            f"schreiben Proxy und Backend auf dieselbe Datei?"
        )

    return GuardrailHealthResponse(
        available=True,
        healthy=healthy,
        stale=veraltet,
        hinweis=hinweis,
        classifier_model=daten.get("classifier_model"),
        fallback_model=daten.get("fallback_model"),
        checked_at=daten.get("checked_at"),
        total=int(daten.get("total", 0)),
        failure_rate=float(daten.get("failure_rate", 0.0)),
        counters={k: int(v) for k, v in zaehler.items()},
    )
