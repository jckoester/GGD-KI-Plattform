"""Löschlauf für Rückmeldungen (ADR-020, ADR-011 §6.2).

**Zwei Fristen, zwei Umgangsweisen.**

*Abgeschlossen* (`done`, `declined`, `spam`): 180 Tage nach dem Statuswechsel wird der
Eintrag gelöscht. Lang genug, um bei einer Regression nachzuschlagen, wann etwas schon
einmal gemeldet war; kurz genug, dass angehängte Chats nicht zum Zweitarchiv der
Chathistorie werden. Der Anhang ist zu diesem Zeitpunkt in aller Regel ohnehin weg — er
fällt schon beim Abschluss, sofern ihn niemand ausdrücklich behalten hat.

*Offen* (`open`, `in_progress`): **wird nicht gelöscht.** Eine unerledigte Meldung
verschwinden zu lassen, hieße, ein Versäumnis der Sichtung aufzuräumen statt es zu
melden. Ab 365 Tagen schreibt der Lauf deshalb eine Warnung — abschließen oder bewusst
behalten ist eine Entscheidung, keine Zeitfrage.

Kein Batch-Limit wie bei den übrigen Läufen: Es geht um einige hundert Zeilen im Jahr,
ohne Dateien auf der Platte und ohne Fremdsysteme.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import perf_counter

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Feedback
from app.feedback.service import ABGESCHLOSSEN, IN_ARBEIT, OFFEN

logger = logging.getLogger(__name__)

# ADR-011 §6.2
AUFBEWAHRUNG_TAGE = 180
HINWEIS_AB_TAGEN = 365


@dataclass
class FeedbackLoeschlauf:
    faellig: int = 0
    geloescht: int = 0
    lange_offen: int = 0
    duration_ms: int = 0


async def cleanup_feedback(
    db: AsyncSession, *, now: datetime | None = None, dry_run: bool = False
) -> FeedbackLoeschlauf:
    """Löscht abgeschlossene Meldungen nach Frist und meldet lange offene."""
    begonnen = perf_counter()
    jetzt = now or datetime.now(timezone.utc)
    stichtag = jetzt - timedelta(days=AUFBEWAHRUNG_TAGE)
    lauf = FeedbackLoeschlauf()

    faellig = (
        Feedback.status.in_(tuple(ABGESCHLOSSEN)),
        Feedback.status_changed_at < stichtag,
    )
    lauf.faellig = int(
        await db.scalar(select(func.count()).select_from(Feedback).where(*faellig)) or 0
    )

    if not dry_run and lauf.faellig:
        ergebnis = await db.execute(delete(Feedback).where(*faellig))
        lauf.geloescht = ergebnis.rowcount or 0
        await db.commit()

    lauf.lange_offen = int(
        await db.scalar(
            select(func.count())
            .select_from(Feedback)
            .where(
                Feedback.status.in_((OFFEN, IN_ARBEIT)),
                Feedback.created_at < jetzt - timedelta(days=HINWEIS_AB_TAGEN),
            )
        )
        or 0
    )
    if lauf.lange_offen:
        logger.warning(
            "%d Rückmeldung(en) sind seit über %d Tagen offen — abschließen oder "
            "bewusst behalten.", lauf.lange_offen, HINWEIS_AB_TAGEN,
        )

    lauf.duration_ms = int((perf_counter() - begonnen) * 1000)
    logger.info(
        "cleanup_feedback fertig faellig=%d geloescht=%d lange_offen=%d dry_run=%s "
        "duration_ms=%d",
        lauf.faellig, lauf.geloescht, lauf.lange_offen, dry_run, lauf.duration_ms,
    )
    return lauf
