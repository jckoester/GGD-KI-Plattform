#!/usr/bin/env python3
"""
Einmaliges Migrations-Skript: Generiert Virtual Keys für alle bestehenden User
in pseudonym_audit, die noch keinen haben.

Verwendung:
    python scripts/migrate_litellm_keys.py
    python scripts/migrate_litellm_keys.py --dry-run --limit 100
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Füge backend-Verzeichnis zum Path hinzu (relativ zum Skript-Ort)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PseudonymAudit
from app.db.session import AsyncSessionLocal
from app.litellm.client import LiteLLMClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def migrate_keys(*, limit: int, dry_run: bool) -> dict:
    """
    Migriert alle User ohne Virtual Key.
    
    Gibt ein Summary-Dict zurück mit:
    - total: Gesamtzahl der User ohne Key
    - processed: Anzahl der verarbeiteten User
    - generated: Anzahl der generierten Keys
    - failed: Anzahl der Fehler
    - skipped: Anzahl der übersprungenen User (bereits Key vorhanden)
    """
    stats = {
        "total": 0,
        "processed": 0,
        "generated": 0,
        "failed": 0,
        "skipped": 0,
    }
    
    client = LiteLLMClient()
    try:
        async with AsyncSessionLocal() as db:
            # Alle User ohne Key laden
            result = await db.execute(
                select(PseudonymAudit)
                .where(PseudonymAudit.litellm_key.is_(None))
                .order_by(PseudonymAudit.created_at.asc())
                .limit(limit) if limit > 0 else select(PseudonymAudit).where(PseudonymAudit.litellm_key.is_(None))
            )
            entries = list(result.scalars().all())
            stats["total"] = len(entries)
            
            if dry_run:
                logger.info("DRY RUN: Würde %d User migrieren", stats["total"])
                stats["processed"] = stats["total"]
                return stats
            
            for entry in entries:
                try:
                    # Key generieren
                    key = await client.generate_key(entry.pseudonym)
                    
                    # Key speichern
                    await db.execute(
                        update(PseudonymAudit)
                        .where(PseudonymAudit.pseudonym == entry.pseudonym)
                        .values(litellm_key=key)
                    )
                    
                    stats["generated"] += 1
                    logger.info("Key generiert für pseudonym=%s", entry.pseudonym)
                    
                except Exception as e:
                    stats["failed"] += 1
                    logger.error("Fehler bei pseudonym=%s: %s", entry.pseudonym, e)
                
                stats["processed"] += 1
                
                # alle 100 User committen
                if stats["processed"] % 100 == 0:
                    await db.commit()
                    logger.info("Fortschritt: %d/%d verarbeitet", stats["processed"], stats["total"])
            
            # Final commit
            await db.commit()
    finally:
        await client.close()
    
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migriert LiteLLM Virtual Keys für bestehende User"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur zählen, keine Keys generieren",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximale Anzahl von Usern zu verarbeiten (0 = alle, Default: 0)",
    )
    args = parser.parse_args()

    if args.limit < 0:
        logger.error("--limit muss >= 0 sein")
        sys.exit(1)

    try:
        stats = asyncio.run(migrate_keys(limit=args.limit, dry_run=args.dry_run))
        
        # Summary
        if args.dry_run:
            logger.info("DRY RUN MODE - Keine Änderungen vorgenommen")
        
        logger.info(
            "Migration abgeschlossen: total=%d processed=%d generated=%d failed=%d skipped=%d",
            stats["total"],
            stats["processed"],
            stats["generated"],
            stats["failed"],
            stats["skipped"],
        )
        
        if stats["failed"] > 0:
            sys.exit(1)
            
    except Exception:
        logger.exception("Migration fehlgeschlagen")
        sys.exit(1)


if __name__ == "__main__":
    main()
