"""Selbstverwaltung persönlicher Zugangstoken (PAT).

Anlegen, auflisten, widerrufen — für die eigene Person, im Profil. Kein Admin-Umweg: Wer
ein Token braucht, weiß selbst, wofür, und ein Antragsweg hätte nur zur Folge, dass
Token länger leben als nötig.

**Dieser Router steht nicht in der Scope-Tabelle** (`app.auth.scopes`), ist für Token
also gesperrt. Das ist kein Versehen: Ein Token, das weitere Token anlegen kann, lässt
sich nicht mehr widerrufen — man widerruft eines und das nächste steht schon bereit.
"""

import logging
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import tokens as token_dienst
from app.auth.dependencies import require_any_role, require_frische_sitzung
from app.auth.jwt import JwtPayload
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tokens", tags=["tokens"])

_LEHRKRAFT_ODER_ADMIN = require_any_role(["teacher", "admin"])


class TokenAnlegen(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scopes: list[str]
    # Datum, keine Dauer: „gültig bis 31.07." ist im Schulalltag die greifbarere Angabe
    # als „gültig für 322 Tage", und das Schuljahresende ist der natürliche Schnitt.
    gueltig_bis: date


class TokenRead(BaseModel):
    id: UUID
    name: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    # Gesetzt: Verbindung eines KI-Programms per OAuth (0.55, AX) — das Profil zeigt sie unter
    # „Verbundene Programme“, nicht als Zugangstoken.
    oauth_client_id: str | None = None

    class Config:
        from_attributes = True


class TokenAngelegt(BaseModel):
    """Die **einzige** Antwort, die den Klartext trägt."""

    token: str
    eintrag: TokenRead


def _als_read(zeile) -> TokenRead:
    return TokenRead.model_validate(zeile)


@router.get("", response_model=list[TokenRead])
async def meine_token(
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_LEHRKRAFT_ODER_ADMIN),
):
    """Alle eigenen Token, jüngste zuerst — auch abgelaufene und widerrufene.

    Widerrufene bleiben sichtbar, weil die Liste sonst die Frage „hatte ich da nicht mal
    eines?" nicht beantworten kann. Der Klartext steht in keiner davon.
    """
    return [_als_read(z) for z in await token_dienst.meine(db, user.sub)]


@router.post("", response_model=TokenAngelegt, status_code=201)
async def token_anlegen(
    payload: TokenAnlegen,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(require_frische_sitzung()),
):
    """Legt ein Token an und gibt den Klartext **einmalig** zurück.

    Nur mit frischer Sitzung (höchstens 15 Minuten alt): Ein gestohlenes Sitzungs-Cookie
    soll sich keinen Dauerzugang ausstellen können, der das Ausloggen überlebt. Ist die
    Sitzung älter, kommt 401 mit `X-Frische-Anmeldung` — die Oberfläche meldet kurz neu an.
    """
    if not ({"teacher", "admin"} & set(user.roles)):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")

    # Ende des gewählten Tages, nicht Mitternacht zu seinem Beginn: Sonst wäre ein Token
    # mit dem heutigen Datum bereits abgelaufen, bevor es das erste Mal benutzt wird.
    gueltig_bis = datetime.combine(payload.gueltig_bis, time.max, tzinfo=timezone.utc)
    try:
        klartext, zeile = await token_dienst.erzeuge(
            db,
            pseudonym=user.sub,
            name=payload.name,
            scopes=payload.scopes,
            gueltig_bis=gueltig_bis,
            rollen=user.roles,
        )
    except token_dienst.TokenFehler as e:
        raise HTTPException(status_code=422, detail=str(e))

    logger.info("Zugangstoken angelegt (%s, %s)", zeile.id, ", ".join(zeile.scopes))
    return TokenAngelegt(token=klartext, eintrag=_als_read(zeile))


@router.delete("/{token_id}", status_code=204)
async def token_widerrufen(
    token_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_LEHRKRAFT_ODER_ADMIN),
):
    """Widerruft ein eigenes Token. Wirkt sofort, auch mitten in einem Sync-Lauf.

    **Ohne Step-up.** Ein Zugang zu *beenden* ist die sichere Richtung; eine Hürde davor
    schützt niemanden und hält im Zweifel jemanden auf, der es eilig hat.
    """
    if not await token_dienst.widerrufe(db, token_id, user.sub):
        raise HTTPException(status_code=404, detail="Token nicht gefunden")


@router.get("/scopes")
async def verfuegbare_scopes(user: JwtPayload = Depends(_LEHRKRAFT_ODER_ADMIN)) -> dict:
    """Die vergebbaren Berechtigungen samt Beschriftung — damit die Oberfläche sie nicht
    doppelt führt und bei einer neuen nicht stillschweigend veraltet."""
    from app.config import settings
    from app.mcp.auth import SCOPE as MCP_SCOPE

    def eintrag(k: str, v: str) -> dict:
        aus = {"key": k, "label": v}
        if hinweis := token_dienst.SCOPE_HINWEIS.get(k):
            aus["hinweis"] = hinweis
        if k == MCP_SCOPE:  # Adresse zum Eintragen im Programm, Anleitung in der Hilfe
            aus["adresse"] = settings.mcp_oeffentliche_url
            aus["hilfe"] = "/help/profil#ki-programme-verbinden"
        return aus

    return {
        # Den Scope für KI-Programme nur anbieten, wenn die Schule die Schnittstelle
        # eingeschaltet hat (F4) — sonst legte man ein Token an, das nirgends hinführt.
        "scopes": [
            eintrag(k, v)
            for k, v in token_dienst.SCOPE_BESCHRIFTUNG.items()
            if k != MCP_SCOPE or (settings.mcp_aktiv and settings.mcp_oeffentliche_url)
        ],
        "max_tage": token_dienst.MAX_GUELTIGKEIT.days,
        "vorschlag_gueltig_bis": (
            date.today() + timedelta(days=token_dienst.MAX_GUELTIGKEIT.days)
        ).isoformat(),
    }
