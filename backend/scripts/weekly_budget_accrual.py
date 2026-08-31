#!/usr/bin/env python3
"""
Wöchentliche Aufstockung der Budget-Obergrenzen (Wochenmodell, 08/2026).

Hebt für jede Nutzerin ``max_budget`` am LiteLLM-User um den konfigurierten Wochenbetrag
an — gedeckelt auf ``vorsprung_wochen`` Wochenbeträge über dem tatsächlichen Verbrauch.
Der Verbrauch wird **nicht** zurückgesetzt; er läuft das Schuljahr durch.

Der Lauf ist **idempotent**: Zweimal in derselben Unterrichtswoche ausgeführt bucht er
einmal. Fällt er aus, holt der nächste Lauf die fehlenden Wochen nach — begrenzt durch
denselben Vorsprung, ein ausgefallener Cron ist also kein Freibrief.

In Ferienwochen tut er nichts.

**Zum Schuljahreswechsel** beginnt die Zählung von vorn: Beim ersten Lauf eines neuen
Schuljahres (erkannt am `schuljahr`-Feld des Merkpostens) werden Obergrenze **und
Verbrauch** zurückgesetzt. Reste wandern also nicht ins nächste Schuljahr — das ist die
Zusage, die auch in der Admin-Oberfläche steht. Es ist der einzige Reset im ganzen Modell
und braucht keinen eigenen Lauf.

Verwendung:
    python scripts/weekly_budget_accrual.py
    python scripts/weekly_budget_accrual.py --dry-run
    python scripts/weekly_budget_accrual.py --stichtag 2026-11-10
    python scripts/weekly_budget_accrual.py --pseudonym <pseudonym>
    python scripts/weekly_budget_accrual.py --neuaufbau   # einmalig nach der Umstellung
"""
import argparse
import asyncio
import logging
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.budget.accrual import merke, plane
from app.budget.exchange import get_current_rate
from app.budget.tiers import get_budget_for, vorsprung_wochen
from app.db.models import BudgetAccrual, PseudonymAudit
from app.db.session import AsyncSessionLocal
from app.litellm.client import LiteLLMClient
from app.planning.calendar import load_school_year

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run(*, dry_run: bool, stichtag: date, pseudonym_filter: str | None,
              neuaufbau: bool = False) -> None:
    cfg = load_school_year()
    counters: dict[str, int] = defaultdict(int)

    async with AsyncSessionLocal() as db:
        eur_usd = await get_current_rate(db)
        stmt = select(PseudonymAudit)
        if pseudonym_filter:
            stmt = stmt.where(PseudonymAudit.pseudonym == pseudonym_filter)
        users = (await db.execute(stmt)).scalars().all()

        logger.info(
            "Schuljahr %s · Stichtag %s · Kurs %.4f · Vorsprung %d Wochen · %d Nutzer",
            cfg.schuljahr, stichtag, eur_usd, vorsprung_wochen(), len(users),
        )

        # Einmal je Lauf, nicht je Nutzer:in: Bei sieben Konten wären es sieben gleiche
        # Zeilen, und die Warnung ginge in der eigenen Wiederholung unter.
        if stichtag < cfg.beginn or stichtag > cfg.ende:
            logger.warning(
                "Der Stichtag %s liegt AUSSERHALB des konfigurierten Schuljahres %s "
                "(%s – %s). Es wird nichts zugeteilt — und zwar bei jedem Lauf, bis "
                "config/school_year.yaml das laufende Schuljahr führt. Die Konten "
                "behalten so lange ihre bisherigen Obergrenzen, und der "
                "Jahreswechsel-Reset löst nicht aus (er hängt am Wechsel des "
                "Config-Jahres). Vorgehen: docs/runbooks/schuljahreswechsel.md",
                stichtag, cfg.schuljahr, cfg.beginn, cfg.ende,
            )

        client = LiteLLMClient()
        try:
            for user in users:
                counters["total"] += 1
                roles = user.roles or [user.role]
                betrag_eur = get_budget_for(roles, user.grade)
                if not betrag_eur:
                    counters["ohne_budget"] += 1
                    continue
                betrag_usd = betrag_eur * eur_usd

                try:
                    # Der Ist-Stand kommt vom Proxy, nicht aus unserer DB: Er ist die
                    # Quelle für Verbrauch UND Grenze, und beide können sich zwischen
                    # zwei Läufen geändert haben (Admin-Eingriff, Bild-Aufrufe).
                    info = await client.get_user(user.pseudonym) or {}
                    zuteilung = await plane(
                        db,
                        user.pseudonym,
                        wochenbetrag_usd=betrag_usd,
                        aktuelle_grenze_usd=info.get("max_budget"),
                        verbrauch_usd=info.get("spend") or 0.0,
                        stichtag=stichtag,
                        cfg=cfg,
                        neuaufbau=neuaufbau,
                    )
                except Exception:
                    logger.exception("Zuteilung nicht planbar pseudonym=%s", user.pseudonym)
                    counters["fehler"] += 1
                    continue

                if not zuteilung.zu_tun:
                    counters[zuteilung.grund or "nichts zu tun"] += 1
                    continue

                if dry_run:
                    logger.info(
                        "[dry-run] %s: %.4f → %.4f (%d Woche(n), bis KW-Index %s)%s",
                        user.pseudonym, info.get("max_budget") or 0.0,
                        zuteilung.neue_grenze_usd, zuteilung.gebuchte_wochen,
                        zuteilung.bis_woche,
                        "  ⟲ Schuljahreswechsel, Verbrauch wird genullt"
                        if zuteilung.jahreswechsel else "",
                    )
                    counters["gebucht"] += 1
                    if zuteilung.jahreswechsel:
                        counters["jahreswechsel"] += 1
                    continue

                try:
                    await client.update_user_budget(
                        user.pseudonym, zuteilung.neue_grenze_usd,
                        # Der einzige Anlass, den Verbrauchszähler anzufassen.
                        spend=0.0 if zuteilung.jahreswechsel else None,
                    )
                except Exception:
                    # Merkposten NICHT fortschreiben — sonst gilt die Woche als gebucht,
                    # obwohl die Grenze unverändert ist, und niemand holt sie nach.
                    logger.exception("Aufstockung fehlgeschlagen pseudonym=%s", user.pseudonym)
                    counters["fehler"] += 1
                    continue

                await merke(
                    db, user.pseudonym,
                    bis_woche=zuteilung.bis_woche, schuljahr=cfg.schuljahr,
                )
                counters["gebucht"] += 1
                if zuteilung.jahreswechsel:
                    counters["jahreswechsel"] += 1
        finally:
            await client.close()

        if not dry_run:
            await db.commit()

    logger.info(
        "weekly_budget_accrual done total=%d gebucht=%d ohne_budget=%d fehler=%d %s",
        counters["total"], counters["gebucht"], counters["ohne_budget"],
        counters["fehler"],
        " ".join(
            f"{k}={v}" for k, v in sorted(counters.items())
            if k not in {"total", "gebucht", "ohne_budget", "fehler"}
        ),
    )


async def _umstellung_bereits_gelaufen() -> bool:
    """Gibt es für das laufende Schuljahr schon Merkposten?

    `merke()` schreibt je Nutzerin einen `budget_accrual`-Eintrag mit Schuljahr, sobald
    der Proxy eine Zuteilung bestätigt hat. Existiert davon einer für das aktuelle
    Schuljahr, hat die Umstellung stattgefunden — dann ist `--neuaufbau` nicht mehr der
    einmalige Sonderfall, für den er gedacht ist.

    Bewusst „irgendeiner", nicht „alle": Nach einem abgebrochenen Lauf wäre eine
    Vollständigkeitsprüfung die falsche Frage. Wer nachziehen will, nimmt den Regellauf —
    der holt fehlende Wochen von selbst nach.
    """
    async with AsyncSessionLocal() as db:
        schuljahr = load_school_year().schuljahr
        treffer = await db.scalar(
            select(BudgetAccrual.pseudonym)
            .where(BudgetAccrual.schuljahr == schuljahr)
            .limit(1)
        )
    return treffer is not None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="nur zeigen, nichts schreiben")
    p.add_argument("--stichtag", type=date.fromisoformat, default=None,
                   help="Datum der Zuteilung (Default: heute)")
    p.add_argument("--pseudonym", default=None, help="nur diese Nutzerin")
    p.add_argument(
        "--neuaufbau", action="store_true",
        help="Obergrenzen aus den Wochenbeträgen NEU setzen statt aufzustocken. "
             "Einmalig nach der Umstellung vom Monatsmodell — verwirft dabei die alte "
             "Grenze, die sonst als schützenswert gälte.",
    )
    p.add_argument(
        "--trotzdem", action="store_true",
        help="--neuaufbau auch dann ausführen, wenn die Umstellung bereits gelaufen ist.",
    )
    args = p.parse_args()

    if args.neuaufbau:
        if asyncio.run(_umstellung_bereits_gelaufen()) and not args.trotzdem:
            logger.error(
                "Die Umstellung ist für dieses Schuljahr bereits gelaufen — "
                "--neuaufbau wird NICHT wiederholt.\n"
                "\n"
                "Ein zweiter Lauf setzt die Grenze auf `Verbrauch + 1 Wochenbetrag` und "
                "verwirft dabei den angesparten Vorsprung. Der Verbrauch wächst, die "
                "Grenze zieht nach — es sieht aus, als erhöhe sich das Budget von selbst.\n"
                "\n"
                "Im Regelbetrieb genügt der wöchentliche Lauf OHNE Schalter; er stockt auf "
                "und kürzt nie. Wer es wirklich braucht: --neuaufbau --trotzdem."
            )
            raise SystemExit(1)

        logger.warning(
            "NEUAUFBAU: bestehende Obergrenzen werden verworfen und aus den "
            "Wochenbeträgen neu gesetzt. Nur nach der Umstellung vom Monatsmodell."
        )

    asyncio.run(run(
        dry_run=args.dry_run,
        stichtag=args.stichtag or date.today(),
        pseudonym_filter=args.pseudonym,
        neuaufbau=args.neuaufbau,
    ))


if __name__ == "__main__":
    main()
