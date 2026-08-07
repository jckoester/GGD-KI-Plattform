#!/usr/bin/env python3
"""
Gleicht Entfall, Vertretung und Verlegung aus dem Stundenplan mit der Jahresplanung ab
(UP-8, Schritt 10a) — für jede Lehrkraft mit hinterlegtem Kürzel.

**Fail-open:** Ein Fehlschlag hinterlässt die Planung unverändert und wird im Status
festgehalten. Slots werden nie verworfen, weil die Quelle kurz nicht antwortet.

Verwendung:
    python scripts/sync_timetable.py
    python scripts/sync_timetable.py --dry-run
    python scripts/sync_timetable.py --wochen 2 --bis 2026-07-10
"""
import argparse
import asyncio
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.crons.calendar_sync_service import run_calendar_sync
from app.db.session import AsyncSessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _parse_date(raw: str | None) -> date | None:
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Ungültiges ISO-Datum: {raw}") from exc


async def run(*, dry_run: bool, wochen: int, bis: date | None) -> int:
    async with AsyncSessionLocal() as db:
        stats = await run_calendar_sync(db, wochen=wochen, bis=bis, dry_run=dry_run)
    logger.info(
        "sync_timetable done lehrkraefte=%d ok=%d fehlgeschlagen=%d geaendert=%d "
        "konflikte=%d verlegungen=%d duration_ms=%d",
        stats.lehrkraefte, stats.erfolgreich, stats.fehlgeschlagen, stats.geaendert,
        stats.konflikte, stats.verlegungen, stats.duration_ms,
    )
    # Einzelne Fehlschläge sind kein Fehler des Laufs — sie stehen im Status und die
    # übrigen Lehrkräfte wurden abgeglichen. Ein Exit-Code ≠ 0 würde die Cron-Überwachung
    # täglich alarmieren, obwohl nichts zu tun ist.
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Stundenplan-Abgleich (UP-8)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Nur rechnen und melden, nichts schreiben")
    parser.add_argument("--wochen", type=int, default=4,
                        help="Wie viele Unterrichtswochen rückwirkend (Vorgabe: 4)")
    parser.add_argument("--bis", type=_parse_date, default=None,
                        help="Referenztag statt heute (ISO)")
    args = parser.parse_args()

    try:
        exit_code = asyncio.run(
            run(dry_run=args.dry_run, wochen=args.wochen, bis=args.bis)
        )
    except Exception:
        logger.exception("sync_timetable fehlgeschlagen")
        sys.exit(1)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
