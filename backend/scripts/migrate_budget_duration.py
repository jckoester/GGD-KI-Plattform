#!/usr/bin/env python3
"""
Einmalige Umstellung der LiteLLM-Nutzer vom Monats- aufs Wochenmodell (08/2026).

Bestandsnutzer tragen ``budget_duration: 1mo`` und damit ein ``budget_reset_at``. Solange
das so bleibt, setzt LiteLLM ihren Verbrauch weiterhin monatlich zurück — der
Wochen-Zuteilungslauf liefe daneben her, ohne dass etwas fehlschlägt. **Der Bestand bliebe
unbemerkt im alten Modell.**

── Warum direkt in der Proxy-Datenbank ──────────────────────────────────────────────

Über ``/user/update`` geht es nicht (gemessen 29.08.2026, ``scripts/budget_reset_probe.py``):

    budget_duration: None    → Zeitraum bleibt unverändert stehen
    budget_duration: ""      → Feld wird leer, aber `budget_reset_at` springt auf den
                               FOLGETAG — der Verbrauch würde täglich genullt, das Budget
                               wäre praktisch unbegrenzt. Schlimmer als vorher.
    budget_duration: "null"  → dasselbe

Der ``UPDATE`` unten setzt beide Spalten auf NULL. Nachgemessen: Virtual Keys bleiben
nutzbar, ``spend`` und Team-Zugehörigkeit bleiben unberührt.

── Die Obergrenze rührt dieser Lauf NICHT an ────────────────────────────────────────

``max_budget`` trägt bei Bestandsnutzern einen **Monatsbetrag** — ein Vielfaches des neuen
Wochenbetrags. Sie müsste also neu aufgebaut werden. Das geschieht aber **nicht hier**:

    Bei LiteLLM bedeutet `max_budget = NULL` *und* `max_budget = 0` gleichermaßen
    **kein Limit** (gemessen 29.08.2026). Wer die Spalte hier leert, öffnet jedes Konto
    unbegrenzt, bis der Zuteilungslauf sie wieder füllt.

Der Neuaufbau gehört deshalb in denselben Lauf, der die Grenzen ohnehin setzt:

    python scripts/migrate_budget_duration.py --verbrauch-zuruecksetzen
    python scripts/weekly_budget_accrual.py --neuaufbau

In dieser Reihenfolge gibt es zu keinem Zeitpunkt ein Konto ohne Limit.

Verwendung:
    python scripts/migrate_budget_duration.py --dry-run
    python scripts/migrate_budget_duration.py
    python scripts/migrate_budget_duration.py --verbrauch-zuruecksetzen
"""
import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

TABELLE = '"LiteLLM_UserTable"'


def _dsn() -> str:
    dsn = os.environ.get("LITELLM_DATABASE_URL")
    if dsn:
        return dsn
    # Ohne gesetzte Umgebung aus der .env lesen (lokaler Lauf außerhalb des Containers).
    env = Path(__file__).resolve().parent.parent.parent / ".env"
    if env.exists():
        for zeile in env.read_text(encoding="utf-8").splitlines():
            zeile = zeile.strip()
            if zeile.startswith("LITELLM_DATABASE_URL="):
                return zeile.partition("=")[2].split("#")[0].strip().strip("'\"")
    raise SystemExit("LITELLM_DATABASE_URL fehlt (Umgebung oder .env).")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="nur zählen, nichts ändern")
    p.add_argument(
        "--verbrauch-zuruecksetzen", action="store_true",
        help="zusätzlich `spend` auf 0 setzen — sinnvoll zum Schuljahresbeginn, "
             "damit der Verbrauch des alten Modells nicht gegen das neue Jahr zählt",
    )
    args = p.parse_args()

    with psycopg2.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT count(*) FROM {TABELLE} "
            "WHERE budget_duration IS NOT NULL OR budget_reset_at IS NOT NULL"
        )
        betroffen = cur.fetchone()[0]
        cur.execute(f"SELECT count(*) FROM {TABELLE}")
        gesamt = cur.fetchone()[0]

        logger.info("LiteLLM-Nutzer gesamt: %d", gesamt)
        logger.info("Noch im Monatsmodell:  %d", betroffen)

        if betroffen == 0:
            logger.info("\nNichts zu tun — der Bestand läuft bereits im Wochenmodell.")
            return 0

        if args.dry_run:
            cur.execute(
                f"SELECT user_id, max_budget, spend, budget_duration, budget_reset_at "
                f"FROM {TABELLE} WHERE budget_duration IS NOT NULL "
                "OR budget_reset_at IS NOT NULL LIMIT 5"
            )
            logger.info("\nBeispiele (max. 5):")
            for uid, mb, sp, bd, br in cur.fetchall():
                logger.info("  %s… max=%s spend=%s duration=%r reset=%s",
                            uid[:12], mb, sp, bd, br)
            logger.info(
                "\n[dry-run] Es würden %d Nutzer umgestellt:\n"
                "  budget_duration → NULL, budget_reset_at → NULL%s",
                betroffen,
                ", spend → 0" if args.verbrauch_zuruecksetzen else "",
            )
            return 0

        felder = "budget_duration = NULL, budget_reset_at = NULL"
        if args.verbrauch_zuruecksetzen:
            felder += ", spend = 0"
        cur.execute(
            f"UPDATE {TABELLE} SET {felder} "
            "WHERE budget_duration IS NOT NULL OR budget_reset_at IS NOT NULL"
        )
        logger.info("\n%d Nutzer umgestellt.", cur.rowcount)

    logger.info(
        "\nNächster Schritt — die Obergrenzen tragen noch Monatsbeträge:\n"
        "    python scripts/weekly_budget_accrual.py --neuaufbau\n"
        "Ohne ihn bleiben sie stehen, bis der Verbrauch sie eingeholt hat; das Wochenmodell\n"
        "wirkt dann monatelang nicht."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
