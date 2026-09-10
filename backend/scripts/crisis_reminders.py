#!/usr/bin/env python3
"""
Erinnert an unerledigte Krisenfälle und warnt vor der Aufbewahrungsgrenze.

Täglich laufen lassen. Verschickt höchstens **zwei** Mails je Lauf (eine Erinnerung,
eine letzte Warnung) — nicht eine je Fall.

⚠️ Dieser Lauf setzt `conversation_flags.last_reminder_at`, und **nur** ein Flag mit
diesem Vermerk verliert später seinen Löschschutz. Läuft er nicht, bleiben geflaggte
Konversationen unbegrenzt liegen. Das ist die sichere Richtung — aber es heißt auch,
dass ein vergessener Cron-Eintrag still zu wachsendem Bestand führt.

Verwendung:
    python scripts/crisis_reminders.py
    python scripts/crisis_reminders.py --dry-run
    python scripts/crisis_reminders.py --now 2026-09-10T06:00:00+00:00
"""
import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.crisis.erinnerung import lauf
from app.db.session import AsyncSessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def _trockenlauf_sender(betreff, text, empfaenger):
    """Zeigt, was verschickt würde — und verschickt nichts."""
    from app.mail import Versandergebnis

    logger.info("[Probelauf] An %d Empfänger: %s\n%s", len(empfaenger), betreff, text)
    return Versandergebnis(False, "Probelauf")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="nichts versenden und nichts vermerken — nur zeigen")
    parser.add_argument("--now", help="Stichtag (ISO-8601), für Tests")
    args = parser.parse_args()

    jetzt = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
    if jetzt.tzinfo is None:
        jetzt = jetzt.replace(tzinfo=timezone.utc)

    if args.dry_run:
        # Der Probelauf darf **nicht** vermerken: Ein gesetzter `last_reminder_at`
        # startete die Löschfrist, ohne dass jemand gewarnt wurde.
        from app.crisis import erinnerung

        async def _kein_vermerk(db, _jetzt):
            logger.info("[Probelauf] `last_reminder_at` wird nicht gesetzt.")
            return 0

        erinnerung._vermerke = _kein_vermerk
        lage = await lauf(AsyncSessionLocal, sender=_trockenlauf_sender, jetzt=jetzt)
    else:
        lage = await lauf(AsyncSessionLocal, jetzt=jetzt)

    logger.info(
        "Krisen-Erinnerungslauf: %d offen, davon %d erinnerungsreif, %d vor der Grenze.",
        lage.offen_gesamt, lage.faellig, lage.vor_loeschung,
    )


if __name__ == "__main__":
    asyncio.run(main())
