"""Benachrichtigung über neue Rückmeldungen (ADR-020, AP3).

**Warum diese Mail mehr sagt als die der Krisenerkennung.** Dort ist der Inhalt nur
nach Zweitfreigabe einsehbar, die Mail meldet deshalb bloß, *dass* etwas zu tun ist.
Hier ist das Gegenteil richtig: Eine Rückmeldung ist an die Administration gerichtet,
und wer am Wochenende liest „drei neue Meldungen", muss sich trotzdem anmelden, um zu
sehen, ob eine davon dringend ist. Kategorie, Rolle, Version und der Anfang des Textes
beantworten das im Postfach.

**Was trotzdem nicht mitkommt:** die freiwillige Kontaktangabe, ein angehängter Chat
und das Pseudonym. Das Postfach kennt keine Zweckbindung und keine Löschfrist — was
dort landet, ist weiterleitbar und bleibt. Der Kontakt ist die einzige Spalte im
System, die einen Klarnamen tragen kann, der Anhang eine Kopie fremder Chatinhalte;
beides gehört in die Oberfläche, nicht in eine Mail.

**Die Dämpfung kommt ohne gemerkten Zustand aus** — wie bei der Krisenerkennung: Sie
zählt die Meldungen im Fenster, statt sich einen letzten Versand zu merken. Ein
gemerkter Zeitpunkt läge im Arbeitsspeicher (weg beim Neustart, je Arbeitsprozess ein
eigener); hier zählt ein `SELECT`, und der ist neustartfest und über Prozesse hinweg
richtig. Der Preis: Scheitert gerade diese eine Mail, schweigen die folgenden im
selben Fenster ebenfalls — die Meldungen bleiben ja im Eingang stehen.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

import sqlalchemy as sa

from app.config import settings
from app.db.models import Feedback

logger = logging.getLogger(__name__)

# Innerhalb dieses Fensters verschickt nur die erste Meldung eine Mail.
DAEMPFUNG = timedelta(hours=1)

BETREFF = "KI-Client: neue Rückmeldung(en)"

# So viel Text wandert in die Mail. Genug, um Dringliches zu erkennen; zu wenig, um
# das Postfach zum Zweitarchiv der Meldungen zu machen.
VORSCHAU = 200

_KATEGORIEN = {"bug": "Fehler", "suggestion": "Vorschlag", "other": "Sonstiges"}
_ROLLEN = {"teacher": "Lehrkraft", "student": "Schüler:in", "admin": "Admin"}


class Eintrag(NamedTuple):
    """Was von einer Meldung in die Mail darf — und nichts sonst.

    Bewusst vier Felder statt des Datensatzes: Wer hier Kontakt oder Pseudonym
    ergänzen wollte, müsste die Struktur ändern, und ein Test hält sie fest.
    """

    kategorie: str
    rolle: str
    version: str
    vorschau: str


def _feedback_url() -> str:
    return f"{settings.frontend_origin.rstrip('/')}/feedback/manage"


def _vorschau(inhalt: str) -> str:
    """Eine Zeile. Zeilenumbrüche würden das Format der Liste zerreißen."""
    einzeilig = " ".join((inhalt or "").split())
    return einzeilig[:VORSCHAU] + ("…" if len(einzeilig) > VORSCHAU else "")


def text(offen: int, eintraege: list[Eintrag]) -> str:
    """Der Mailtext. Rein, damit sich prüfen lässt, was **nicht** drinsteht."""
    zeilen = [
        "In der KI-Plattform sind neue Rückmeldungen eingegangen.",
        "",
        f"Neu in der letzten Stunde: {len(eintraege)}",
        f"Unerledigt insgesamt: {offen}",
        "",
    ]
    for e in eintraege:
        kategorie = _KATEGORIEN.get(e.kategorie, e.kategorie)
        rolle = _ROLLEN.get(e.rolle, e.rolle)
        zeilen.append(f"[{kategorie} · {rolle} · {e.version}] {e.vorschau}")
    zeilen += [
        "",
        f"Zur Übersicht: {_feedback_url()}",
        "",
        "Diese Nachricht nennt bewusst weder Pseudonym noch Kontaktangabe noch einen",
        "angehängten Chat. Das alles steht nur in der Plattform selbst.",
    ]
    return "\n".join(zeilen)


async def _lage(db, jetzt: datetime) -> tuple[int, int, list[Eintrag]]:
    """(Meldungen im Fenster, unerledigte insgesamt, die Einträge des Fensters)."""
    offene_stati = ("open", "in_progress")
    seit = jetzt - DAEMPFUNG

    im_fenster = await db.scalar(
        sa.select(sa.func.count()).select_from(Feedback).where(Feedback.created_at > seit)
    )
    offen = await db.scalar(
        sa.select(sa.func.count())
        .select_from(Feedback)
        .where(Feedback.status.in_(offene_stati))
    )
    zeilen = await db.execute(
        sa.select(Feedback.category, Feedback.role, Feedback.app_version, Feedback.content)
        .where(Feedback.created_at > seit)
        .order_by(Feedback.created_at)
    )
    eintraege = [
        Eintrag(kategorie=k, rolle=r, version=v, vorschau=_vorschau(inhalt))
        for k, r, v, inhalt in zeilen.all()
    ]
    return int(im_fenster or 0), int(offen or 0), eintraege


async def benachrichtige(session_factory, *, sender=None, jetzt: datetime | None = None) -> bool:
    """Verschickt die Mail, wenn diese Meldung die erste im Fenster ist.

    :param sender: einspeisbar für Tests; sonst :func:`app.mail.sende`.
    :returns: ob versendet wurde.
    """
    from app.mail import sende

    sender = sender or sende
    jetzt = jetzt or datetime.now(timezone.utc)

    async with session_factory() as db:
        im_fenster, offen, eintraege = await _lage(db, jetzt)

    if im_fenster > 1:
        logger.info(
            "Feedback-Benachrichtigung unterdrückt: %d Meldungen in der letzten Stunde, "
            "es wurde bereits benachrichtigt.", im_fenster,
        )
        return False

    ergebnis = await sender(BETREFF, text(offen, eintraege), list(settings.feedback_notify_to))
    return ergebnis.versendet
