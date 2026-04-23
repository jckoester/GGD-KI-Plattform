#!/usr/bin/env python
"""
Setup-Skript zum einmaligen Anlegen der Phase-1-Teams in LiteLLM.
Idempotent: bereits vorhandene Teams werden nicht als Fehler gewertet.
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.litellm.client import LiteLLMClient
from app.litellm.teams import STUDENT_TEAM_PREFIX, TEACHER_TEAM_ID

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def create_team(client: LiteLLMClient, team_id: str) -> str:
    """Legt ein Team an und gibt den Status zurück."""
    try:
        await client.create_team(team_id)
        return "created"
    except Exception as e:
        logger.error("Fehler beim Anlegen von Team %s: %s", team_id, e)
        return "error"


async def main() -> int:
    """Hauptfunktion: alle Phase-1-Teams anlegen."""
    client = LiteLLMClient()
    try:
        # Teacher-Team
        teacher_status = await create_team(client, TEACHER_TEAM_ID)
        if teacher_status == "created":
            logger.info("Team %s angelegt", TEACHER_TEAM_ID)
        elif teacher_status == "error":
            logger.error("Team %s konnte nicht angelegt werden", TEACHER_TEAM_ID)
            return 1
        else:
            logger.info("Team %s bereits vorhanden", TEACHER_TEAM_ID)

        # Schüler-Jahrgangs-Teams
        for grade in settings.student_grades:
            team_id = f"{STUDENT_TEAM_PREFIX}{grade}"
            status = await create_team(client, team_id)
            if status == "created":
                logger.info("Team %s angelegt", team_id)
            elif status == "error":
                logger.error("Team %s konnte nicht angelegt werden", team_id)
                return 1
            else:
                logger.info("Team %s bereits vorhanden", team_id)

        logger.info("Alle Phase-1-Teams erfolgreich bearbeitet")
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
