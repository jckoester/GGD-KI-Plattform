"""Antwortbewertung: Daumen hoch/runter an einer Modellantwort (0.31, Päckchen T, ADR-020).

Zwei Orte, ein Vorgang:

- ``message_ratings`` — die Bewertung selbst, eine je Antwort, **ohne Pseudonym**: Wem sie
  gehört, folgt aus Nachricht → Konversation. Sie geht mit der Nachricht.
- ``rating_counts`` — dieselbe Bewertung als Wochenzähler je Assistent, Modell und Rolle
  (Plan F5). Die Zähler überdauern das Löschen der Chats.

Beide ändern sich in **einer** Transaktion. Umentscheiden und Zurücknehmen korrigieren die
Zeile, in die die erste Bewertung zählte (Woche aus ``created_at``, gespeicherte ``rolle``) —
sonst wanderte eine Bewertung beim Umentscheiden in eine spätere Woche.

**Keine Bewertung in Test- und Vorschau-Chats** (Plan F6): Dort prüfen Lehrkräfte gezielt;
dafür gibt es das Feedback-Formular. In der Vorschau selbst sperrt ohnehin die Schreibsperre
(`app.auth.vorschau`, der Endpunkt steht nicht in ``ERLAUBT``).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import JwtPayload
from app.context.vorab_statistik import woche_von
from app.db.models import Conversation, Message, MessageRating, RatingCount
from app.db.session import get_db
from app.ratelimit.dependency import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["bewertung"])


def rolle_fuer_zaehler(rollen: list[str]) -> str:
    """Lehrkräfte und Admins zählen als Lehrkraft, alle übrigen als Schüler:in."""
    return "teacher" if {"teacher", "admin"} & set(rollen) else "student"


def bewertbar(konversation: Conversation) -> bool:
    """Gibt es an diesem Chat Daumen? Nicht in Test- und Vorschau-Chats (Plan F6)."""
    return not konversation.is_test and konversation.preview_context is None


async def _zaehle(db: AsyncSession, *, woche, assistant_id, modell, rolle, wert: int, delta: int):
    """Den Zähler für ``wert`` (±1) um ``delta`` (±1) ändern.

    Hochzählen legt die Zeile bei Bedarf an. Herunterzählen ändert nur eine vorhandene Zeile
    und nie unter null: Ist der Assistent inzwischen gelöscht, sind seine Zeilen mit ihm
    gegangen, und die Antwort trägt `assistant_id` leer — das Herunterzählen träfe sonst die
    Zeile „ohne Assistent“, in die diese Bewertung nie gezählt hat.
    """
    spalte = "plus" if wert > 0 else "minus"
    if delta > 0:
        stmt = insert(RatingCount).values(woche=woche, assistant_id=assistant_id, modell=modell,
                                          rolle=rolle, **{spalte: 1})
        await db.execute(stmt.on_conflict_do_update(
            constraint="uq_rating_counts_schluessel",
            set_={spalte: getattr(RatingCount, spalte) + 1},
        ))
        return
    await db.execute(
        sa.update(RatingCount)
        .where(RatingCount.woche == woche,
               RatingCount.assistant_id.is_not_distinct_from(assistant_id),
               RatingCount.modell.is_not_distinct_from(modell),
               RatingCount.rolle == rolle)
        .values({spalte: sa.func.greatest(getattr(RatingCount, spalte) - 1, 0)})
    )


async def bewerte(
    db: AsyncSession, *, pseudonym: str, rollen: list[str], message_id: UUID, wert: int,
    jetzt: datetime | None = None,
) -> int | None:
    """Bewertung setzen (``1``/``-1``) oder zurücknehmen (``0``). Gibt die neue Bewertung zurück.

    404 für fremde und unbekannte Nachrichten — gleich, damit sich fremde Kennungen nicht
    ertasten lassen.
    """
    jetzt = jetzt or datetime.now(timezone.utc)
    # Die Nachricht sperren: Zwei schnelle Klicks auf dieselbe Antwort laufen nacheinander,
    # nicht verschränkt — sonst zählte der Zähler doppelt.
    zeile = (await db.execute(
        sa.select(Message, Conversation)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Message.id == message_id)
        .with_for_update(of=Message)
    )).one_or_none()
    if zeile is None or zeile.Conversation.pseudonym != pseudonym:
        raise HTTPException(status_code=404, detail="Nachricht nicht gefunden")
    nachricht, konversation = zeile.Message, zeile.Conversation
    if nachricht.role != "assistant":
        raise HTTPException(status_code=422, detail="Bewerten lassen sich nur Antworten.")
    if nachricht.ersetzt_am is not None:
        raise HTTPException(status_code=409, detail="Diese Antwort wurde ersetzt.")
    if not bewertbar(konversation):
        raise HTTPException(
            status_code=403, detail="In Test- und Vorschau-Chats gibt es keine Bewertung.",
        )

    vorher = await db.get(MessageRating, message_id)
    schluessel = {"assistant_id": nachricht.assistant_id, "modell": nachricht.model}

    if vorher is None:
        if wert == 0:
            return None
        db.add(MessageRating(message_id=message_id, rating=wert,
                             rolle=rolle_fuer_zaehler(rollen), created_at=jetzt, updated_at=jetzt))
        await _zaehle(db, woche=woche_von(jetzt), rolle=rolle_fuer_zaehler(rollen),
                      wert=wert, delta=1, **schluessel)
        neu = wert
    elif wert == vorher.rating:
        return wert
    else:
        woche, rolle = woche_von(vorher.created_at), vorher.rolle
        await _zaehle(db, woche=woche, rolle=rolle, wert=vorher.rating, delta=-1, **schluessel)
        if wert == 0:
            await db.delete(vorher)
            neu = None
        else:
            vorher.rating = wert
            vorher.updated_at = jetzt
            await _zaehle(db, woche=woche, rolle=rolle, wert=wert, delta=1, **schluessel)
            neu = wert

    await db.commit()
    return neu


async def bewertungen(db: AsyncSession, message_ids: list[UUID]) -> dict[UUID, int]:
    """Die Bewertungen zu diesen Nachrichten — für die Nachrichtenliste eines Chats."""
    if not message_ids:
        return {}
    ergebnis = await db.execute(
        sa.select(MessageRating.message_id, MessageRating.rating)
        .where(MessageRating.message_id.in_(message_ids))
    )
    return {kennung: wert for kennung, wert in ergebnis.all()}


# ── Bewertungen eigener Assistenten (0.33, Päckchen AK) ─────────────────────────

#: Ab so vielen Bewertungen je Rolle sieht die Erstellerin Zahlen (Plan F1). Die Schwelle setzt
#: der **Server** durch: Unter ihr stehen weder Zahlen noch Anteil in der Antwort. Benutzen nur
#: wenige Schüler:innen einen Assistenten, wäre schon „1 Daumen runter“ eine Aussage über eine
#: bestimmte Person — die Oberfläche auszublenden genügte nicht, die Zahl stünde im Netzwerk.
MINDEST_EIGENE = 10


class Rollenstand(BaseModel):
    """Daumen einer Rolle — oder nur ``zu_wenige``, solange die Mindestzahl nicht erreicht ist."""

    zu_wenige: bool
    plus: int | None = None
    minus: int | None = None
    #: Anteil „hilfreich“ in Prozent, gerundet.
    anteil: int | None = None


class BewertungZusammenfassung(BaseModel):
    """Gesamtstand eines Assistenten über alle Wochen und Modelle (Plan F2: nur gesamt),
    Schüler:innen und Lehrkräfte getrennt (F3)."""

    schueler: Rollenstand
    lehrkraefte: Rollenstand


def _stand(plus: int, minus: int) -> Rollenstand:
    gesamt = plus + minus
    if gesamt < MINDEST_EIGENE:
        return Rollenstand(zu_wenige=True)
    return Rollenstand(zu_wenige=False, plus=plus, minus=minus, anteil=round(100 * plus / gesamt))


async def zusammenfassungen(
    db: AsyncSession, assistant_ids: list[int],
) -> dict[int, BewertungZusammenfassung]:
    """Gesamtstand je Assistent aus `rating_counts` — mit der Mindestzahl je Rolle.

    Kein Verlauf je Woche (F2): Er verkleinerte die Mengen und machte Rückschlüsse leichter.
    """
    summen: dict[tuple[int, str], tuple[int, int]] = {}
    if assistant_ids:
        for aid, rolle, plus, minus in (await db.execute(
            sa.select(RatingCount.assistant_id, RatingCount.rolle,
                      sa.func.sum(RatingCount.plus), sa.func.sum(RatingCount.minus))
            .where(RatingCount.assistant_id.in_(assistant_ids))
            .group_by(RatingCount.assistant_id, RatingCount.rolle)
        )).all():
            summen[(aid, rolle)] = (int(plus or 0), int(minus or 0))
    return {
        aid: BewertungZusammenfassung(
            schueler=_stand(*summen.get((aid, "student"), (0, 0))),
            lehrkraefte=_stand(*summen.get((aid, "teacher"), (0, 0))),
        )
        for aid in assistant_ids
    }


class BewertungIn(BaseModel):
    #: 1 = hilfreich, -1 = nicht hilfreich, 0 = zurücknehmen.
    rating: Literal[-1, 0, 1]


class BewertungOut(BaseModel):
    rating: int | None = None


@router.put("/messages/{message_id}/rating")
async def rate_message(
    message_id: UUID,
    daten: BewertungIn,
    current_user: JwtPayload = Depends(rate_limit("bewertung")),
    db: AsyncSession = Depends(get_db),
) -> BewertungOut:
    """Eine eigene Antwort bewerten, umbewerten oder die Bewertung zurücknehmen."""
    neu = await bewerte(db, pseudonym=current_user.sub, rollen=list(current_user.roles),
                        message_id=message_id, wert=daten.rating)
    return BewertungOut(rating=neu)
