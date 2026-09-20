"""Die Regeln des Feedback-Kanals (ADR-020).

**Warum der Missbrauchsschutz ohne eigene Tabelle auskommt.** Sperre und Tageslimit
lesen sich aus den Meldungen selbst: dreimal `spam` in 30 Tagen sperrt 14 Tage, zwanzig
Meldungen in 24 Stunden sind genug. Eine Sperrtabelle daneben müsste gepflegt,
aufgeräumt und bei jeder Statuskorrektur nachgezogen werden — und wäre doch nur eine
zweite Meinung über dieselben Daten.

**Reihenfolge der Prüfungen.** Sperre vor Tageslimit vor Snapshot: Wer gesperrt ist,
soll nicht erst erfahren, dass sein Anhang in Ordnung gewesen wäre.

Die Statusmaschine für die Sichtung kommt in AP3 in dieselbe Datei — beide Seiten
sollen dieselbe Auffassung davon haben, was ein Status bedeutet.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Feedback
from app.feedback import snapshot
from app.feedback.schemas import FeedbackCreate, FeedbackOut

logger = logging.getLogger(__name__)

# ── Missbrauchsschutz (ADR-010 §1.2/1.3 Nachtrag) ────────────────────────────────
SPAM_SCHWELLE = 3
SPAM_FENSTER = timedelta(days=30)
SPERRE = timedelta(days=14)
TAGESLIMIT = 20
TAGESFENSTER = timedelta(hours=24)

# Zustände, aus denen eine Meldung nicht mehr zurückgezogen werden kann.
OFFEN = "open"


def _jetzt(jetzt: datetime | None) -> datetime:
    return jetzt or datetime.now(timezone.utc)


async def gesperrt_bis(
    db: AsyncSession, pseudonym: str, *, jetzt: datetime | None = None
) -> datetime | None:
    """Bis wann dieses Pseudonym gesperrt ist — `None`, wenn es frei ist.

    Gezählt werden die `spam`-Einträge der letzten 30 Tage. Ab dem dritten läuft die
    Sperre **ab dem jüngsten** von ihnen, also `max(status_changed_at) + 14 Tage`: Die
    Sperre setzt mit dem dritten Eintrag ein, und der ist der zuletzt gesetzte. Der
    älteste (`min`) wäre der erste Verstoß und ließe die Sperre zu früh enden.
    """
    jetzt = _jetzt(jetzt)
    anzahl, juengster = (
        await db.execute(
            select(func.count(), func.max(Feedback.status_changed_at)).where(
                Feedback.pseudonym == pseudonym,
                Feedback.status == "spam",
                Feedback.status_changed_at > jetzt - SPAM_FENSTER,
            )
        )
    ).one()
    if anzahl < SPAM_SCHWELLE or juengster is None:
        return None
    ende = juengster + SPERRE
    return ende if ende > jetzt else None


async def _tageslage(
    db: AsyncSession, pseudonym: str, *, jetzt: datetime
) -> tuple[int, datetime | None]:
    """Wie viele Meldungen in den letzten 24 Stunden — und ab wann wieder Platz ist."""
    anzahl, aeltester = (
        await db.execute(
            select(func.count(), func.min(Feedback.created_at)).where(
                Feedback.pseudonym == pseudonym,
                Feedback.created_at > jetzt - TAGESFENSTER,
            )
        )
    ).one()
    return anzahl, aeltester


async def pruefe_grenzen(
    db: AsyncSession, pseudonym: str, *, jetzt: datetime | None = None
) -> None:
    """Sperre und Tageslimit. Wirft 403 bzw. 429, sonst still."""
    jetzt = _jetzt(jetzt)

    ende = await gesperrt_bis(db, pseudonym, jetzt=jetzt)
    if ende is not None:
        logger.info("feedback_blocked pseudonym=%s bis=%s", pseudonym, ende.isoformat())
        raise HTTPException(
            status_code=403,
            detail=f"Feedback vorübergehend gesperrt bis {ende.strftime('%d.%m.%Y')}.",
        )

    anzahl, aeltester = await _tageslage(db, pseudonym, jetzt=jetzt)
    if anzahl >= TAGESLIMIT:
        # Frei wird ein Platz, wenn die älteste Meldung aus dem Fenster fällt — kein
        # pauschales „in 24 Stunden", das wäre fast immer zu lang.
        frei_ab = (aeltester or jetzt) + TAGESFENSTER
        wartezeit = max(1, int((frei_ab - jetzt).total_seconds()))
        raise HTTPException(
            status_code=429,
            detail="Heute wurden schon viele Meldungen gesendet. Bitte später erneut.",
            headers={"Retry-After": str(wartezeit)},
        )


async def erstelle(
    db: AsyncSession,
    daten: FeedbackCreate,
    *,
    pseudonym: str,
    rolle: str,
    jetzt: datetime | None = None,
) -> Feedback:
    """Legt eine Meldung an — nach Sperre, Tageslimit und (optional) Snapshot."""
    jetzt = _jetzt(jetzt)
    await pruefe_grenzen(db, pseudonym, jetzt=jetzt)

    anhang = None
    if daten.attach_conversation_id is not None:
        anhang = await snapshot.lade(db, daten.attach_conversation_id, pseudonym)
        if anhang is None:
            raise HTTPException(status_code=404, detail="Konversation nicht gefunden")

    eintrag = Feedback(
        pseudonym=pseudonym,
        role=rolle,
        category=daten.category,
        content=daten.content,
        contact=daten.contact,
        app_version=daten.app_version,
        route=daten.route,
        assistant_id=daten.assistant_id,
        user_agent=daten.user_agent,
        viewport=daten.viewport,
        conversation_snapshot=anhang,
    )
    db.add(eintrag)
    await db.commit()
    await db.refresh(eintrag)

    # Ohne Inhalt: Was gemeldet wurde, steht in der Tabelle und geht niemanden an, der
    # ins Log sieht (ADR-010 Nachtrag).
    logger.info(
        "feedback_created pseudonym=%s id=%s kategorie=%s anhang=%s zeichen=%d",
        pseudonym, eintrag.id, eintrag.category, anhang is not None, len(daten.content),
    )
    return eintrag


async def eigene(db: AsyncSession, pseudonym: str) -> list[Feedback]:
    """Die eigenen Meldungen, neueste zuerst."""
    ergebnis = await db.execute(
        select(Feedback)
        .where(Feedback.pseudonym == pseudonym)
        .order_by(Feedback.created_at.desc())
    )
    return list(ergebnis.scalars().all())


async def ziehe_zurueck(db: AsyncSession, pseudonym: str, feedback_id: UUID) -> None:
    """Löscht eine eigene, noch unbearbeitete Meldung.

    404 für fremd und nicht vorhanden (kein Hinweis auf fremde Existenz), 409, sobald
    die Sichtung sie angefasst hat: Was bereits bearbeitet wird, verschwindet nicht
    unter den Händen der sichtenden Person.
    """
    eintrag = await db.scalar(
        select(Feedback).where(
            Feedback.id == feedback_id, Feedback.pseudonym == pseudonym
        )
    )
    if eintrag is None:
        raise HTTPException(status_code=404, detail="Meldung nicht gefunden")
    if eintrag.status != OFFEN:
        raise HTTPException(
            status_code=409,
            detail="Die Meldung wird bereits bearbeitet und kann nicht mehr zurückgezogen werden.",
        )
    await db.delete(eintrag)
    await db.commit()
    logger.info("feedback_withdrawn pseudonym=%s id=%s", pseudonym, feedback_id)


def nach_aussen(eintrag: Feedback) -> FeedbackOut:
    """Die Sicht der meldenden Person auf ihre eigene Meldung.

    `spam` erscheint als `declined` **ohne** Begründung (ADR-020): Der Status ist ein
    Urteil der Sichtung über die Meldung, kein Gesprächsangebot. Wer ihn als solchen
    angezeigt bekäme, widerspräche — und der Kanal ist bewusst eine Einbahnstraße.
    """
    status = eintrag.status
    antwort = eintrag.admin_reply
    if status == "spam":
        status, antwort = "declined", None
    return FeedbackOut(
        id=eintrag.id,
        category=eintrag.category,
        content=eintrag.content,
        contact=eintrag.contact,
        app_version=eintrag.app_version,
        route=eintrag.route,
        assistant_id=eintrag.assistant_id,
        status=status,
        admin_reply=antwort,
        resolved_in_version=eintrag.resolved_in_version,
        has_snapshot=eintrag.conversation_snapshot is not None,
        created_at=eintrag.created_at,
        status_changed_at=eintrag.status_changed_at,
    )
