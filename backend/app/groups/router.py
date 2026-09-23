"""Endpunkte für Beitrittscodes (AP4).

Getrennt von `app/api/groups.py`, weil dort Gruppen *verwaltet* werden und hier eine
Berechtigung ausgegeben und eingelöst wird — zwei verschiedene Rechte-Lagen: Das Ausgeben
darf nur die Gruppenlehrkraft, das Einlösen jede angemeldete Schüler:in.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_any_role
from app.auth.jwt import JwtPayload
from app.db.session import get_db
from app.groups.beitritt import (
    aktueller_code,
    beitritte_je_tag,
    erzeuge_code,
    loese_ein,
    nimm_beitritte_zurueck,
    pruefe_code,
    widerrufe_codes,
)
from app.planning.permissions import require_group_teacher
from app.ratelimit.dependency import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/groups", tags=["group-join"])

_LEHRKRAFT = require_any_role(["teacher", "admin"])


def _als_antwort(code, jetzt: datetime, tage) -> dict:
    lage = pruefe_code(code, jetzt)
    return {
        "id": str(code.id),
        "code": code.code,
        "erstellt_am": code.erstellt_am.isoformat(),
        "gueltig_bis": code.gueltig_bis.isoformat(),
        "gueltig": lage.gueltig,
        # Nur Zahlen, keine Pseudonyme: Die Lehrkraft soll erkennen, **wann** zu viele
        # dazukamen, nicht **wer** es war.
        "beitritte": [{"tag": t.tag.isoformat(), "anzahl": t.anzahl} for t in tage],
    }


@router.get("/{group_id}/join-code")
async def code_lesen(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_LEHRKRAFT),
) -> dict:
    """Der aktuelle Code der Gruppe samt Beitritten je Tag.

    ⚠️ **Keine Drossel auf dem Lesepfad.** Die läge sonst auf einer Ansicht, die beim
    normalen Arbeiten mehrfach aufgerufen wird — dieselbe Falle wie beim Feedback-Kanal,
    wo `rate_limit` zunächst auch das Lesen der eigenen Meldungen traf.
    """
    await require_group_teacher(group_id, user, db)
    code = await aktueller_code(db, group_id)
    if code is None:
        return {"code": None}
    return _als_antwort(code, datetime.now(UTC), await beitritte_je_tag(db, code.id))


@router.post("/{group_id}/join-code", status_code=201)
async def code_erzeugen_endpunkt(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_LEHRKRAFT),
) -> dict:
    """Einen Code ausgeben oder erneuern. Der bisherige verfällt dabei."""
    await require_group_teacher(group_id, user, db)
    code = await erzeuge_code(db, group_id, user.sub)
    await db.commit()
    logger.info("beitrittscode_erzeugt pseudonym=%s gruppe=%s", user.sub, group_id)
    return _als_antwort(code, datetime.now(UTC), [])


@router.delete("/{group_id}/join-code", status_code=204)
async def code_widerrufen(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_LEHRKRAFT),
) -> None:
    """Den Code ungültig machen. Bereits Beigetretene bleiben Mitglied."""
    await require_group_teacher(group_id, user, db)
    await widerrufe_codes(db, group_id)
    await db.commit()
    logger.info("beitrittscode_widerrufen pseudonym=%s gruppe=%s", user.sub, group_id)


class RuecknahmeRequest(BaseModel):
    """Welche Menge zurückgenommen werden soll."""

    # `None` = die ganze Code-Runde. Ein einzelner Tag daraus, wenn die Runde über
    # mehrere Tage lief und nur einer schiefging.
    tag: date | None = None


@router.post("/{group_id}/join-code/rollback")
async def beitritte_zuruecknehmen(
    group_id: int,
    body: RuecknahmeRequest,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_LEHRKRAFT),
) -> dict:
    """Fehlbeitritte zurücknehmen — als Menge, nie je Person.

    Ohne Namen ist eine Einzelauswahl nicht sicher bedienbar: Wer die falsche Zeile
    trifft, entfernt eine berechtigte Person und merkt es nicht. Die Lehrkraft wählt
    deshalb die Code-Runde oder einen Tag daraus.

    Der Code wird dabei **ungültig** — sonst treten dieselben Falschen sofort wieder bei.
    """
    await require_group_teacher(group_id, user, db)
    code = await aktueller_code(db, group_id)
    if code is None:
        raise HTTPException(404, "Für diese Gruppe gibt es keinen Code.")

    entfernt = await nimm_beitritte_zurueck(db, code.id, body.tag)
    await db.commit()
    logger.info(
        "beitritte_zurueckgenommen pseudonym=%s gruppe=%s tag=%s entfernt=%d",
        user.sub, group_id, body.tag, entfernt,
    )
    return {"entfernt": entfernt}


class BeitrittRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)


@router.post("/join", status_code=201)
async def beitreten(
    body: BeitrittRequest,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(rate_limit("group_join")),
) -> dict:
    """Einer Gruppe per Code beitreten.

    ⚠️ **Nur Schüler:innen.** Der Weg macht `role_in_group='student'`; kooperativ
    unterrichtende Kolleg:innen sind ein eigener Fall und kommen nicht hierüber hinein
    (Entscheidung Jan, F3).

    Die Drossel sitzt **nur hier**, nicht auf dem Lesepfad: Sonst sperrte sich eine
    Klasse, die gleichzeitig beitritt, gegenseitig aus.
    """
    if "teacher" in user.roles or "admin" in user.roles:
        raise HTTPException(
            403,
            "Beitrittscodes sind für Schüler:innen. Kooperativ unterrichtete Gruppen "
            "werden anders zusammengeführt.",
        )

    code, lage = await loese_ein(db, body.code, user.sub)
    if not lage.gueltig:
        await db.rollback()
        # „unbekannt" deckt auch **widerrufen** ab: Wer einen fremden Code probiert,
        # soll nicht erfahren, ob es ihn gibt.
        if lage.grund == "abgelaufen":
            raise HTTPException(410, "Dieser Code ist abgelaufen. Bitte einen neuen erfragen.")
        raise HTTPException(404, "Dieser Code gilt nicht.")

    await db.commit()
    logger.info("gruppe_beigetreten pseudonym=%s gruppe=%s", user.sub, code.group_id)
    return {"group_id": code.group_id}
