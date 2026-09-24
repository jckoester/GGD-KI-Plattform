"""Endpunkte für Beitrittscodes (AP4).

Getrennt von `app/api/groups.py`, weil dort Gruppen *verwaltet* werden und hier eine
Berechtigung ausgegeben und eingelöst wird — zwei verschiedene Rechte-Lagen: Das Ausgeben
darf nur die Gruppenlehrkraft, das Einlösen jede angemeldete Schüler:in.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_any_role
from app.auth.jwt import JwtPayload
from app.db.session import get_db
from app.groups.angebote import (
    hebe_ignorieren_auf,
    ignoriere,
    kandidaten,
    lade_angebote,
    FachFehlt,
    lege_an,
    ordne_zu,
)
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


# ── Angebote für neue SSO-Unterrichtsgruppen (AP2) ───────────────────────────


@router.get("/offers")
async def angebote_lesen(
    mit_ignorierten: bool = False,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_LEHRKRAFT),
) -> dict:
    """Die eigenen Angebote samt Gruppen, denen sie zugeordnet werden könnten.

    Kandidaten und Angebote kommen **zusammen**: Die Oberfläche soll die Frage stellen
    können, ohne eine zweite Runde zu drehen — und die Belege („12 Stunden, 4 Chats")
    entstehen ohnehin in einer Abfrage.
    """
    angebote = await lade_angebote(db, user.sub, mit_ignorierten=mit_ignorierten)
    gruppen = await kandidaten(db, user.sub) if angebote else []
    return {
        "angebote": [
            {
                "id": str(a.id),
                "sso_group_id": a.sso_group_id,
                "name": a.name,
                "fach": a.fach,
                # Ob „Neu anlegen“ überhaupt gehen kann. Ohne Fach entsteht keine
                # Unterrichtsgruppe (`lege_an`); einen Knopf anzubieten, der mit 422
                # antwortet, wäre schlechter als keiner — er sieht nach einem Weg aus.
                "kann_angelegt_werden": a.subject_id is not None,
                "ignoriert": a.ignoriert,
            }
            for a in angebote
        ],
        "gruppen": [
            {"id": k.id, "name": k.name, "fach": k.fach, "beleg": k.beleg}
            for k in gruppen
        ],
    }


class ZuordnenRequest(BaseModel):
    group_id: int


@router.post("/offers/{angebot_id}/assign")
async def angebot_zuordnen(
    angebot_id: UUID,
    body: ZuordnenRequest,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_LEHRKRAFT),
) -> dict:
    """Das Angebot einer vorhandenen Gruppe zuordnen."""
    try:
        ergebnis = await ordne_zu(db, angebot_id, body.group_id, user.sub)
    except LookupError as exc:
        await db.rollback()
        raise HTTPException(404, str(exc)) from None
    except PermissionError:
        await db.rollback()
        raise HTTPException(403, "Sie sind keine Lehrkraft dieser Gruppe.") from None
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(409, str(exc)) from None
    await db.commit()
    logger.info(
        "angebot_zugeordnet pseudonym=%s angebot=%s gruppe=%s geerbt_entfernt=%d",
        user.sub, angebot_id, ergebnis.group_id, ergebnis.geerbte_entfernt,
    )
    return {
        "group_id": ergebnis.group_id,
        "geerbte_entfernt": ergebnis.geerbte_entfernt,
    }


@router.post("/offers/{angebot_id}/create", status_code=201)
async def angebot_anlegen(
    angebot_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_LEHRKRAFT),
) -> dict:
    """Aus dem Angebot eine neue Unterrichtsgruppe machen."""
    try:
        group_id = await lege_an(db, angebot_id, user.sub)
    except FachFehlt as exc:
        # 422, nicht 404: Das Angebot gibt es, es taugt nur nicht zum Anlegen.
        await db.rollback()
        raise HTTPException(422, str(exc)) from None
    except LookupError as exc:
        await db.rollback()
        raise HTTPException(404, str(exc)) from None
    await db.commit()
    logger.info("angebot_angelegt pseudonym=%s angebot=%s gruppe=%s",
                user.sub, angebot_id, group_id)
    return {"group_id": group_id}


@router.post("/offers/{angebot_id}/ignore", status_code=204)
async def angebot_ignorieren(
    angebot_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_LEHRKRAFT),
) -> None:
    """Ablehnen. Die Frage kehrt nicht zurück — rücknehmbar bleibt sie trotzdem."""
    try:
        await ignoriere(db, angebot_id, user.sub)
    except LookupError as exc:
        await db.rollback()
        raise HTTPException(404, str(exc)) from None
    await db.commit()


@router.delete("/offers/{angebot_id}/ignore", status_code=204)
async def angebot_wieder_zeigen(
    angebot_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: JwtPayload = Depends(_LEHRKRAFT),
) -> None:
    """Die Ablehnung zurücknehmen — sonst wäre ein Fehlklick endgültig."""
    try:
        await hebe_ignorieren_auf(db, angebot_id, user.sub)
    except LookupError as exc:
        await db.rollback()
        raise HTTPException(404, str(exc)) from None
    await db.commit()
