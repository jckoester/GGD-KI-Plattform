"""Erinnerung an unerledigte Krisenfälle und die letzte Warnung vor der Obergrenze.

Läuft täglich (`scripts/crisis_reminders.py`). Zwei Anlässe, **eine** Sammelmail je
Lauf — nicht eine je Fall: Zwanzig Einzelmails an dasselbe Postfach sind keine
zwanzigfache Aufmerksamkeit, sondern gar keine.

**Die Kopplung an die Obergrenze.** Der Lauf setzt `last_reminder_at`, und nur ein
Flag mit diesem Vermerk verliert später seinen Schutz (`cleanup_service`). Läuft der
Lauf nicht, wird auch nichts gelöscht. Das ist die sichere Richtung: Ungefragt zu
löschen wäre der schlechtere Ausfall als zu lange aufzubewahren.

Der Vermerk wird auch dann gesetzt, wenn **kein** SMTP eingerichtet ist — der
Versand schreibt den Inhalt dann ins Log (`app/mail`). Sonst hinge die Löschfrist
an einer Einstellung, die mit ihr nichts zu tun hat.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from app.config import settings
from app.db.models import ConversationFlag

logger = logging.getLogger(__name__)

OFFENE_STATI = ("open", "under_review")

# Nach der ersten Erinnerung höchstens wöchentlich erneut.
ERINNERUNGSABSTAND = timedelta(days=7)

BETREFF_ERINNERUNG = "Krisen-Hinweis: unerledigte Fälle"
BETREFF_WARNUNG = "Krisen-Hinweis: Fälle werden bald gelöscht"


@dataclass(frozen=True)
class Lage:
    """Was der Lauf vorgefunden hat — die Grundlage von Text und Protokoll."""

    faellig: int          # überfällig und erinnerungsreif
    offen_gesamt: int     # alle unerledigten
    aeltestes_tage: int | None
    vor_loeschung: int    # innerhalb der letzten Warnfrist
    loeschung_in_tagen: int


def _flags_url() -> str:
    return f"{settings.frontend_origin.rstrip('/')}/flags"


def erinnerungstext(lage: Lage) -> str:
    """Wie die Benachrichtigung: nennt Zahlen und den Weg, sonst nichts."""
    zeilen = [
        f"In der KI-Plattform liegen {lage.offen_gesamt} unerledigte Hinweise aus der",
        "Krisenerkennung. Davon sind sie seit mehr als",
        f"{settings.crisis_reminder_days} Tagen unbearbeitet: {lage.faellig}.",
    ]
    if lage.aeltestes_tage is not None:
        zeilen.append(f"Ältester Fall: seit {lage.aeltestes_tage} Tagen.")
    zeilen += ["", f"Zur Übersicht: {_flags_url()}", "",
               "Diese Nachricht nennt bewusst weder Person noch Kategorie noch Inhalt."]
    return "\n".join(zeilen)


def warnungstext(lage: Lage) -> str:
    """Die letzte Warnung. Sie nennt die Folge, weil sie sonst keine Warnung ist."""
    return "\n".join([
        f"{lage.vor_loeschung} unerledigte Hinweise aus der Krisenerkennung erreichen",
        f"in den nächsten {lage.loeschung_in_tagen} Tagen die Aufbewahrungsgrenze von",
        f"{settings.crisis_max_open_days} Tagen.",
        "",
        "Danach werden die zugehörigen Konversationen wie jede andere gelöscht —",
        "eine Einsicht ist dann nicht mehr möglich.",
        "",
        f"Zur Übersicht: {_flags_url()}",
    ])


def _offen():
    return ConversationFlag.status.in_(OFFENE_STATI)


async def lage_ermitteln(db, jetzt: datetime) -> Lage:
    faellig_ab = jetzt - timedelta(days=settings.crisis_reminder_days)
    erinnert_vor = jetzt - ERINNERUNGSABSTAND
    warnung_ab = jetzt - timedelta(
        days=settings.crisis_max_open_days - settings.crisis_final_warning_days
    )

    faellig = await db.scalar(
        sa.select(sa.func.count()).select_from(ConversationFlag).where(
            _offen(),
            ConversationFlag.flagged_at < faellig_ab,
            sa.or_(
                ConversationFlag.last_reminder_at.is_(None),
                ConversationFlag.last_reminder_at < erinnert_vor,
            ),
        )
    )
    offen_gesamt = await db.scalar(
        sa.select(sa.func.count()).select_from(ConversationFlag).where(_offen())
    )
    aeltestes = await db.scalar(
        sa.select(sa.func.min(ConversationFlag.flagged_at)).where(_offen())
    )
    vor_loeschung = await db.scalar(
        sa.select(sa.func.count()).select_from(ConversationFlag).where(
            _offen(), ConversationFlag.flagged_at < warnung_ab
        )
    )

    tage = None
    if aeltestes is not None:
        if aeltestes.tzinfo is None:
            aeltestes = aeltestes.replace(tzinfo=timezone.utc)
        tage = (jetzt - aeltestes).days

    return Lage(
        faellig=int(faellig or 0),
        offen_gesamt=int(offen_gesamt or 0),
        aeltestes_tage=tage,
        vor_loeschung=int(vor_loeschung or 0),
        loeschung_in_tagen=settings.crisis_final_warning_days,
    )


async def _vermerke(db, jetzt: datetime) -> int:
    """`last_reminder_at` auf allen erinnerten Fällen setzen."""
    faellig_ab = jetzt - timedelta(days=settings.crisis_reminder_days)
    erinnert_vor = jetzt - ERINNERUNGSABSTAND
    ergebnis = await db.execute(
        sa.update(ConversationFlag)
        .where(
            _offen(),
            ConversationFlag.flagged_at < faellig_ab,
            sa.or_(
                ConversationFlag.last_reminder_at.is_(None),
                ConversationFlag.last_reminder_at < erinnert_vor,
            ),
        )
        .values(last_reminder_at=jetzt)
    )
    return ergebnis.rowcount or 0


async def lauf(session_factory, *, sender=None, jetzt: datetime | None = None) -> Lage:
    """Ein Durchgang. Gibt die vorgefundene Lage zurück (für Protokoll und Tests)."""
    from app.mail import sende

    sender = sender or sende
    jetzt = jetzt or datetime.now(timezone.utc)
    empfaenger = list(settings.crisis_notify_to)

    async with session_factory() as db:
        lage = await lage_ermitteln(db, jetzt)

        if lage.faellig:
            await sender(BETREFF_ERINNERUNG, erinnerungstext(lage), empfaenger)
            # **Nach** dem Versand vermerken, aber unabhängig von seinem Ausgang:
            # Der Vermerk startet die Löschfrist, und die darf nicht daran hängen,
            # ob ein Mailserver gerade erreichbar war.
            vermerkt = await _vermerke(db, jetzt)
            await db.commit()
            logger.info("Erinnerung an %d Fälle versendet, %d vermerkt.",
                        lage.faellig, vermerkt)

        if lage.vor_loeschung:
            await sender(BETREFF_WARNUNG, warnungstext(lage), empfaenger)
            logger.warning(
                "Letzte Warnung: %d Fälle erreichen in %d Tagen die Aufbewahrungsgrenze.",
                lage.vor_loeschung, lage.loeschung_in_tagen,
            )

        if not lage.faellig and not lage.vor_loeschung:
            logger.info("Keine erinnerungsreifen Krisenfälle (%d offen insgesamt).",
                        lage.offen_gesamt)

    return lage
