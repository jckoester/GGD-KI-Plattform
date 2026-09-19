from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.calendar.base import CalendarSourceError
from app.calendar.service import KUERZEL_PREFERENCE_KEY, validate_kuerzel
from app.db.session import get_db
from app.preferences.service import get_preferences, patch_preferences
from app.ui.levels import STUFEN_SCHLUESSEL, load_ui_levels

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("")
async def read_preferences(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await get_preferences(db, current_user.sub)


@router.patch("")
async def update_preferences(
    updates: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if KUERZEL_PREFERENCE_KEY in updates:
        # Geprüft, bevor irgendetwas gespeichert wird: Ein Tippfehler soll hier auffallen
        # und nicht als stiller Nicht-Abruf Wochen später (UP-8 Schritt 3).
        try:
            updates[KUERZEL_PREFERENCE_KEY] = await validate_kuerzel(
                updates[KUERZEL_PREFERENCE_KEY]
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except CalendarSourceError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Das Kürzel kann derzeit nicht geprüft werden: {exc}",
            ) from None
    if STUFEN_SCHLUESSEL in updates:
        updates[STUFEN_SCHLUESSEL] = _pruefe_stufe(
            updates[STUFEN_SCHLUESSEL], current_user.roles
        )
    return await patch_preferences(db, current_user.sub, updates)


def _pruefe_stufe(wert, rollen: list[str]) -> int:
    """Die Darstellungsstufe, bevor sie gespeichert wird.

    Geprüft statt geklemmt: Ein Wert außerhalb des Bereichs kommt nicht aus der
    Oberfläche, sondern aus einem Fehler oder von Hand. Ihn stillschweigend zu
    korrigieren, verbärge beides. Beim **Lesen** wird dagegen geklemmt — dort darf ein
    Altwert nie zu einer leeren Navigation führen (`stufe_fuer`).
    """
    stufen = load_ui_levels().fuer(rollen)
    if stufen is None:
        raise HTTPException(
            status_code=422,
            detail="Für diese Rolle gibt es keine Darstellungsstufen.",
        )
    try:
        stufe = int(wert)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Stufe muss eine Zahl sein.") from None
    if not 1 <= stufe <= stufen.hoechste:
        raise HTTPException(
            status_code=422,
            detail=f"Stufe muss zwischen 1 und {stufen.hoechste} liegen.",
        )
    return stufe
