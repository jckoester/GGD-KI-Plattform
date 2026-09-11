"""Der eigentliche Versand. Siehe Paket-Docstring für die Grundsatzentscheidungen."""
import asyncio
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate

from app.config import settings

logger = logging.getLogger(__name__)


class MailNichtKonfiguriert(RuntimeError):
    """`SMTP_HOST` fehlt — es kann nicht versendet werden."""


@dataclass(frozen=True)
class Versandergebnis:
    """Was der Versuch ergeben hat.

    Kein bloßes `bool`: „nicht konfiguriert" ist etwas anderes als „gescheitert",
    und die Aufrufer sollen das unterscheiden können, ohne den Log zu lesen.
    """

    versendet: bool
    grund: str | None = None


def ist_konfiguriert() -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


def _nachricht(betreff: str, text: str, empfaenger: list[str]) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = betreff
    msg["From"] = settings.smtp_from
    # ⚠️ Empfänger stehen in `Bcc`, nicht in `To`: Die Liste ist die der Personen mit
    # Krisen-Zuständigkeit. Wer eine solche Mail weiterleitet, gäbe sonst mit, wer
    # sonst noch zuständig ist — eine Personalauskunft, die niemand angefordert hat.
    msg["To"] = settings.smtp_from
    msg["Bcc"] = ", ".join(empfaenger)
    msg["Date"] = formatdate(localtime=True)
    # Automatische Antworten und Abwesenheitsnotizen unterdrücken: Ein Postfach mit
    # Urlaubsschaltung schickte sonst auf jede Erinnerung eine Antwort zurück.
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(text)
    return msg


def _versende_blockierend(msg: EmailMessage) -> None:
    """Der blockierende Teil — läuft in einem eigenen Thread."""
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
        if settings.smtp_starttls:
            server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


async def sende(betreff: str, text: str, empfaenger: list[str]) -> Versandergebnis:
    """Verschickt eine Nachricht. Wirft nicht — der Aufrufer ist nie der Nutzer.

    Ein Fehlschlag darf weder einen Chat noch einen Cron-Lauf abbrechen; er gehört
    ins Log und in das Ergebnis.
    """
    if not empfaenger:
        logger.warning("Mail „%s“ nicht versendet: keine Empfänger konfiguriert.", betreff)
        return Versandergebnis(False, "keine Empfänger")

    if not ist_konfiguriert():
        # Bewusst `warning`, nicht `debug`: Im Produktivsystem ist das ein Befund.
        logger.warning(
            "Mail „%s“ nicht versendet: SMTP ist nicht konfiguriert "
            "(SMTP_HOST/SMTP_FROM). Inhalt wäre gewesen:\n%s",
            betreff, text,
        )
        return Versandergebnis(False, "nicht konfiguriert")

    try:
        await asyncio.to_thread(_versende_blockierend, _nachricht(betreff, text, empfaenger))
    except Exception as exc:  # noqa: BLE001 — jede Ursache endet hier gleich
        logger.exception("Mailversand „%s“ fehlgeschlagen: %s", betreff, exc)
        return Versandergebnis(False, str(exc))

    logger.info("Mail „%s“ an %d Empfänger versendet.", betreff, len(empfaenger))
    return Versandergebnis(True)


def pruefe_beim_start() -> None:
    """Halbe Konfiguration beim Start melden — nicht bei der ersten Krise.

    Bewusst **keine** Ausnahme: Mail ist nicht der Zweck dieser Anwendung, und ein
    Tippfehler in der Absenderadresse soll den Chat nicht abschalten. Ein `error` im
    Log ist die richtige Lautstärke — laut genug zum Finden, leise genug zum
    Weiterlaufen.
    """
    if settings.smtp_host and not settings.smtp_from:
        logger.error(
            "SMTP_HOST ist gesetzt, SMTP_FROM fehlt — es wird nichts versendet. "
            "Krisen-Benachrichtigungen landen still im Log."
        )
    elif settings.smtp_from and not settings.smtp_host:
        logger.error(
            "SMTP_FROM ist gesetzt, SMTP_HOST fehlt — es wird nichts versendet."
        )
    elif not settings.smtp_host:
        logger.info("Kein SMTP konfiguriert — Benachrichtigungen gehen nur ins Log.")
