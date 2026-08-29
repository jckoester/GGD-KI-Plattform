#!/usr/bin/env python3
"""
Monatlicher Abgleich der LiteLLM-Team-Zugehörigkeit für alle Nutzer.

Hieß bis 08/2026 ``monthly_budget_reconcile`` und setzte zusätzlich die Budgets. Das tut
er **nicht mehr**: Seit der Umstellung aufs Wochenmodell ist ``max_budget`` die kumulierte
Zuteilung, die ``weekly_budget_accrual.py`` fortschreibt. Würde dieser Lauf sie weiterhin
auf den Stufenbetrag setzen, machte er die Ansammlung mehrerer Wochen mit einem Schlag
zunichte — ohne Fehler, ohne Hinweis.

Verwendung:
    python scripts/monthly_team_reconcile.py
    python scripts/monthly_team_reconcile.py --dry-run
    python scripts/monthly_team_reconcile.py --limit 10
    python scripts/monthly_team_reconcile.py --pseudonym <pseudonym>
"""
import argparse
import asyncio
import logging
import sys
from collections import defaultdict
from pathlib import Path

# Füge backend-Verzeichnis zum Path hinzu (relativ zum Skript-Ort)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.db.models import PseudonymAudit
from app.db.session import AsyncSessionLocal
from app.litellm.client import LiteLLMClient
from app.litellm.team_service import reconcile_user_team
from app.litellm.teams import get_target_team_id
from app.litellm.user_service import _extract_current_team_ids

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run(
    *, dry_run: bool, limit: int, pseudonym_filter: str | None
) -> None:
    """Hauptlogik: Alle Nutzer durchgehen und ihre Team-Zugehörigkeit angleichen."""
    async with AsyncSessionLocal() as db:

        stmt = select(PseudonymAudit)
        if pseudonym_filter:
            stmt = stmt.where(PseudonymAudit.pseudonym == pseudonym_filter)
        if limit > 0:
            stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        users = result.scalars().all()

    counters = defaultdict(int)
    client = LiteLLMClient()
    try:
        for user in users:
            counters["total"] += 1
            roles = [user.role]

            try:
                target_team_id = get_target_team_id(roles, user.grade)
            except ValueError:
                logger.info(
                    "Kein Zielteam ableitbar pseudonym=%s role=%s grade=%s",
                    user.pseudonym, user.role, user.grade
                )
                counters["skipped"] += 1
                continue

            try:
                if not dry_run:
                    user_info = await client.get_user(user.pseudonym)
                    current_ids = _extract_current_team_ids(user_info)
                    result = await reconcile_user_team(
                        client, user.pseudonym, target_team_id, current_ids
                    )
                    if result["unchanged"]:
                        counters["team_unchanged"] += 1
                    else:
                        counters["team_updated"] += 1
                        logger.info(
                            "Team synchronisiert pseudonym=%s added=%s removed=%s",
                            user.pseudonym, result["added"], result["removed"]
                        )
                else:
                    counters["team_unchanged"] += 1
            except Exception:
                logger.exception("Team-Reconcile fehlgeschlagen pseudonym=%s", user.pseudonym)
                counters["team_failed"] += 1

    finally:
        await client.close()

    logger.info(
        "monthly_team_reconcile done total=%d "
        "team_updated=%d team_unchanged=%d team_failed=%d skipped=%d",
        counters["total"],
        counters["team_updated"],
        counters["team_unchanged"],
        counters["team_failed"],
        counters["skipped"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monatlicher Abgleich der LiteLLM-Team-Zugehörigkeit"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Alle Berechnungen durchführen, keine LiteLLM-Calls",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximal N User verarbeiten (Default: 0 = unbegrenzt)",
    )
    parser.add_argument(
        "--pseudonym",
        type=str,
        default=None,
        help="Nur einen bestimmten User verarbeiten",
    )
    args = parser.parse_args()

    try:
        asyncio.run(
            run(
                dry_run=args.dry_run,
                limit=args.limit,
                pseudonym_filter=args.pseudonym,
            )
        )
    except Exception:
        logger.exception("monthly_team_reconcile fehlgeschlagen")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
