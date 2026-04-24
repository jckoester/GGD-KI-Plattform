#!/usr/bin/env python3
"""
Monatliche Budget- und Team-Reconciliation für alle Nutzer.

Verwendung:
    python scripts/monthly_budget_reconcile.py
    python scripts/monthly_budget_reconcile.py --dry-run
    python scripts/monthly_budget_reconcile.py --limit 10
    python scripts/monthly_budget_reconcile.py --pseudonym <pseudonym>
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

from app.budget.exchange import get_current_rate
from app.budget.tiers import get_budget_for
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
    """Hauptlogik: Alle Nutzer durchgehen, Budgets und Teams aktualisieren."""
    async with AsyncSessionLocal() as db:
        eur_usd = await get_current_rate(db)
        logger.info("Wechselkurs: %.6f EUR/USD", eur_usd)

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

            # Phase A: Budget
            try:
                max_budget_eur, budget_duration = get_budget_for(roles, user.grade)
                max_budget_usd = round(max_budget_eur * eur_usd, 2) if max_budget_eur else None
                if not dry_run:
                    await client.update_user_budget(
                        user.pseudonym, max_budget_usd, budget_duration
                    )
                    logger.debug(
                        "Budget aktualisiert pseudonym=%s max_budget_usd=%s budget_duration=%s",
                        user.pseudonym, max_budget_usd, budget_duration
                    )
                counters["budget_updated"] += 1
            except Exception:
                logger.exception("Budget-Update fehlgeschlagen pseudonym=%s", user.pseudonym)
                counters["budget_failed"] += 1

            # Phase B: Team
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
        "monthly_budget_reconcile done total=%d budget_updated=%d budget_failed=%d "
        "team_updated=%d team_unchanged=%d team_failed=%d skipped=%d eur_usd=%.6f",
        counters["total"],
        counters["budget_updated"],
        counters["budget_failed"],
        counters["team_updated"],
        counters["team_unchanged"],
        counters["team_failed"],
        counters["skipped"],
        eur_usd,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monatliche Budget- und Team-Reconciliation für alle Nutzer"
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
        logger.exception("monthly_budget_reconcile fehlgeschlagen")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
