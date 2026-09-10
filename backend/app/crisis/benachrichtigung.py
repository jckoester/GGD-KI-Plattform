"""Benachrichtigung über Krisenfälle (ADR-008, AP2).

**Was die Mail sagt — und was nicht.** Der Inhalt eines geflaggten Chats ist nur
über das Vier-Augen-Verfahren einsehbar (ADR-008 Teil 5–7). Eine Mail, die
Kategorie, Pseudonym oder gar Text mitschickte, liefe daran vorbei: Sie landet in
einem Postfach, das keine Zweitfreigabe kennt, und ist danach beliebig
weiterleitbar. Sie meldet deshalb, **dass** etwas zu tun ist, nicht **was**
passiert ist.

**Warum die Dämpfung ohne Zustand auskommt.** Eine Klasse, die dasselbe Wort
ausprobiert, löst zwanzig Flags aus; die einundzwanzigste Mail liest niemand mehr.
Gedämpft wird deshalb — aber nicht über eine gemerkte „letzte Mail": Die läge im
Arbeitsspeicher (weg beim Neustart, je Arbeitsprozess eine eigene) oder verlangte
eine Tabelle für eine Nebensache. Stattdessen zählt die Benachrichtigung, wie viele
Flags im Fenster liegen: **Nur das erste verschickt.** Das ist zustandslos,
neustartfest und über mehrere Prozesse hinweg richtig.

Der Preis: Scheitert gerade diese eine Mail, schweigen die folgenden im selben
Fenster ebenfalls. Aufgefangen wird das von der täglichen Erinnerung (AP3) — die
Fälle bleiben ja offen.
"""
import logging
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from app.config import settings
from app.db.models import ConversationFlag

logger = logging.getLogger(__name__)

# Innerhalb dieses Fensters verschickt nur das erste Flag eine Mail.
DAEMPFUNG = timedelta(hours=1)

BETREFF = "Krisen-Hinweis: neuer Fall"


def _flags_url() -> str:
    return f"{settings.frontend_origin.rstrip('/')}/flags"


def text(offen: int, aelteste_tage: int | None) -> str:
    """Der Mailtext. Rein, damit sich prüfen lässt, was **nicht** drinsteht.

    `offen` ist die Zahl der unerledigten Fälle insgesamt, nicht die des Augenblicks:
    Wer die Mail liest, will wissen, was ihn erwartet, nicht was gerade eintraf.
    """
    zeilen = [
        "In der KI-Plattform liegt ein neuer Hinweis aus der Krisenerkennung vor.",
        "",
        f"Unerledigte Fälle insgesamt: {offen}",
    ]
    if aelteste_tage is not None:
        zeilen.append(
            "Ältester unerledigter Fall: "
            + ("heute eingegangen" if aelteste_tage == 0 else f"seit {aelteste_tage} Tagen")
        )
    zeilen += [
        "",
        f"Zur Übersicht: {_flags_url()}",
        "",
        "Diese Nachricht nennt bewusst weder Person noch Kategorie noch Inhalt.",
        "Einsicht in einen Chat ist nur nach Antrag und Zweitfreigabe möglich —",
        "und nur in der Plattform selbst.",
    ]
    return "\n".join(zeilen)


async def _lage(db, jetzt: datetime) -> tuple[int, int, int | None]:
    """(Flags im Dämpfungsfenster, unerledigte insgesamt, Alter des ältesten)."""
    offene_stati = ("open", "under_review")

    im_fenster = await db.scalar(
        sa.select(sa.func.count())
        .select_from(ConversationFlag)
        .where(ConversationFlag.flagged_at > jetzt - DAEMPFUNG)
    )
    offen = await db.scalar(
        sa.select(sa.func.count())
        .select_from(ConversationFlag)
        .where(ConversationFlag.status.in_(offene_stati))
    )
    aeltestes = await db.scalar(
        sa.select(sa.func.min(ConversationFlag.flagged_at))
        .where(ConversationFlag.status.in_(offene_stati))
    )
    tage = None
    if aeltestes is not None:
        if aeltestes.tzinfo is None:
            aeltestes = aeltestes.replace(tzinfo=timezone.utc)
        tage = (jetzt - aeltestes).days
    return int(im_fenster or 0), int(offen or 0), tage


async def benachrichtige(session_factory, *, sender=None, jetzt: datetime | None = None) -> bool:
    """Verschickt die Benachrichtigung, wenn dieses Flag das erste im Fenster ist.

    :param sender: einspeisbar für Tests; sonst :func:`app.mail.sende`.
    :returns: ob versendet wurde.
    """
    from app.mail import sende

    sender = sender or sende
    jetzt = jetzt or datetime.now(timezone.utc)

    async with session_factory() as db:
        im_fenster, offen, tage = await _lage(db, jetzt)

    if im_fenster > 1:
        logger.info(
            "Krisen-Benachrichtigung unterdrückt: %d Flags in der letzten Stunde, "
            "es wurde bereits benachrichtigt.", im_fenster,
        )
        return False

    ergebnis = await sender(BETREFF, text(offen, tage), list(settings.crisis_notify_to))
    return ergebnis.versendet
