"""Auslieferung der Darstellungsstufen an die Oberfläche.

Der Endpunkt liefert **nur die Zuordnung**, nicht die Entscheidung: Was eine Nutzer:in
sehen darf, steht im Rollenmodell; was ihr gezeigt wird, entscheidet die Oberfläche
anhand dieser Liste und der eigenen Stufe. Siehe `app/ui/levels.py`.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.ui.levels import Stufe, load_ui_levels

router = APIRouter(prefix="/ui", tags=["ui"])


class UiLevelsResponse(BaseModel):
    """Die Stufen der eigenen Rolle.

    `rolle` ist die **wirksame** Rolle, nicht der volle Rollensatz — Admin zählt als
    Lehrkraft. `null` heißt: für diese Rolle sind keine Stufen hinterlegt, die Oberfläche
    zeigt dann alles (der sichere Rückfall: lieber zu viel als eine leere Navigation).
    """

    rolle: str | None
    startstufe: int
    hoechste: int
    stufen: list[Stufe]


@router.get("/levels", response_model=UiLevelsResponse)
async def get_ui_levels(
    current_user: JwtPayload = Depends(get_current_user),
) -> UiLevelsResponse:
    cfg = load_ui_levels()
    for name in ("teacher", "student"):
        if name in current_user.roles and name in cfg.rollen:
            r = cfg.rollen[name]
            return UiLevelsResponse(
                rolle=name, startstufe=r.startstufe, hoechste=r.hoechste, stufen=r.stufen
            )
    return UiLevelsResponse(rolle=None, startstufe=1, hoechste=1, stufen=[])
