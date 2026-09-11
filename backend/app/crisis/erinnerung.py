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
from app.db.models import ConversationAccessRequest, ConversationFlag

logger = logging.getLogger(__name__)

OFFENE_STATI = ("open", "under_review")

# Nach der ersten Erinnerung höchstens wöchentlich erneut.
ERINNERUNGSABSTAND = timedelta(days=7)

BETREFF_ERINNERUNG = "Krisen-Hinweis: unerledigte Fälle"
BETREFF_WARNUNG = "Krisen-Hinweis: Fälle werden bald gelöscht"
BETREFF_ANTRAEGE = "Krisen-Einsicht: Anträge warten auf Freigabe"


@dataclass(frozen=True)
class Lage:
    """Was der Lauf vorgefunden hat — die Grundlage von Text und Protokoll."""

    faellig: int          # überfällig und erinnerungsreif
    offen_gesamt: int     # alle unerledigten
    aeltestes_tage: int | None
    vor_loeschung: int    # innerhalb der letzten Warnfrist
    loeschung_in_tagen: int
    # Einsicht-Anträge, die auf Zweitfreigabe warten. Getrennt geführt, weil sie an
    # ein **anderes** Postfach gehen (die `review`-Personen) — siehe `lauf`.
    antraege_faellig: int = 0        # überfällig und erinnerungsreif
    antraege_gesamt: int = 0         # alle wartenden
    antraege_aeltestes_tage: int | None = None


def _flags_url() -> str:
    return f"{settings.frontend_origin.rstrip('/')}/flags"


def _review_url() -> str:
    return f"{settings.frontend_origin.rstrip('/')}/review"


def _alter_in_tagen(zeitpunkt: datetime | None, jetzt: datetime) -> int | None:
    """Alter in Tagen; naive Zeitstempel gelten als UTC.

    SQLite und ältere Bestandszeilen liefern gelegentlich `tzinfo=None`; ohne diese
    Angleichung wirft der Vergleich `TypeError` mitten im Cron-Lauf.
    """
    if zeitpunkt is None:
        return None
    if zeitpunkt.tzinfo is None:
        zeitpunkt = zeitpunkt.replace(tzinfo=timezone.utc)
    return (jetzt - zeitpunkt).days


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


def antragserinnerungstext(lage: Lage) -> str:
    """Die Mahnung an die `review`-Personen.

    Nennt Zahlen und den Weg, sonst nichts — wie die übrigen Texte. Dass ein Antrag
    wartet, ist keine vertrauliche Angabe; *worum* es geht, sehr wohl.
    """
    zeilen = [
        f"In der KI-Plattform warten {lage.antraege_gesamt} Anträge auf Einsicht in",
        "einen geflaggten Chat auf die Zweitfreigabe. Davon liegen seit mehr als",
        f"{settings.crisis_reminder_days} Tagen unbearbeitet: {lage.antraege_faellig}.",
    ]
    if lage.antraege_aeltestes_tage is not None:
        zeilen.append(f"Ältester Antrag: seit {lage.antraege_aeltestes_tage} Tagen.")
    zeilen += [
        "",
        "Solange ein Antrag wartet, steht die Bearbeitung des Falls still.",
        "",
        f"Zur Freigabe: {_review_url()}",
    ]
    return "\n".join(zeilen)


def _offen():
    return ConversationFlag.status.in_(OFFENE_STATI)


def _wartend():
    return ConversationAccessRequest.status == "pending"


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

    # ── Einsicht-Anträge, dieselbe Frist, eigener Vermerk ──────────────────────
    antraege_faellig = await db.scalar(
        sa.select(sa.func.count()).select_from(ConversationAccessRequest).where(
            _wartend(),
            ConversationAccessRequest.requested_at < faellig_ab,
            sa.or_(
                ConversationAccessRequest.last_reminder_at.is_(None),
                ConversationAccessRequest.last_reminder_at < erinnert_vor,
            ),
        )
    )
    antraege_gesamt = await db.scalar(
        sa.select(sa.func.count()).select_from(ConversationAccessRequest).where(_wartend())
    )
    aeltester_antrag = await db.scalar(
        sa.select(sa.func.min(ConversationAccessRequest.requested_at)).where(_wartend())
    )

    return Lage(
        faellig=int(faellig or 0),
        offen_gesamt=int(offen_gesamt or 0),
        aeltestes_tage=_alter_in_tagen(aeltestes, jetzt),
        vor_loeschung=int(vor_loeschung or 0),
        loeschung_in_tagen=settings.crisis_final_warning_days,
        antraege_faellig=int(antraege_faellig or 0),
        antraege_gesamt=int(antraege_gesamt or 0),
        antraege_aeltestes_tage=_alter_in_tagen(aeltester_antrag, jetzt),
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


async def _vermerke_antraege(db, jetzt: datetime) -> int:
    """Dasselbe für die Anträge — eigene Spalte, eigener Rhythmus (Migration 0060)."""
    faellig_ab = jetzt - timedelta(days=settings.crisis_reminder_days)
    erinnert_vor = jetzt - ERINNERUNGSABSTAND
    ergebnis = await db.execute(
        sa.update(ConversationAccessRequest)
        .where(
            _wartend(),
            ConversationAccessRequest.requested_at < faellig_ab,
            sa.or_(
                ConversationAccessRequest.last_reminder_at.is_(None),
                ConversationAccessRequest.last_reminder_at < erinnert_vor,
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

        # ⚠️ **Eigene Mail an ein anderes Postfach.** Die wartenden Anträge gehören
        # nicht in die Sammelmail oben: Freigeben soll, wer *nicht* beantragt hat
        # (ADR-008 Teil 6). Wären beide Listen dieselbe, hebelte die Erinnerung
        # das Vier-Augen-Prinzip aus, ohne dass es auffiele.
        if lage.antraege_faellig:
            await sender(
                BETREFF_ANTRAEGE,
                antragserinnerungstext(lage),
                list(settings.crisis_review_notify_to),
            )
            # Wie oben: **nach** dem Versand, aber unabhängig von seinem Ausgang.
            vermerkt = await _vermerke_antraege(db, jetzt)
            await db.commit()
            logger.info("Erinnerung an %d wartende Anträge versendet, %d vermerkt.",
                        lage.antraege_faellig, vermerkt)

        if not lage.faellig and not lage.vor_loeschung and not lage.antraege_faellig:
            logger.info(
                "Keine erinnerungsreifen Krisenfälle (%d Fälle offen, %d Anträge wartend).",
                lage.offen_gesamt, lage.antraege_gesamt,
            )

    return lage
