#!/usr/bin/env python3
"""
Assistenten aus config/assistants.yaml (oder assistants.example.yaml) in die DB anlegen.

Idempotent anhand des Namens: Existiert bereits ein Assistent gleichen Namens,
wird er übersprungen.

Verwendung (aus backend/):
    python scripts/seed_assistants.py
    python scripts/seed_assistants.py --config /pfad/zur/assistants.yaml
    python scripts/seed_assistants.py --dry-run

Standardpfad: config/assistants.yaml, Fallback: config/assistants.example.yaml
"""
import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import Assistant

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_SCRIPT_DIR = Path(__file__).resolve().parent
# Docker: /app/scripts → /app/config/
# Lokal:  backend/scripts → backend/../config/
_cfg_base_docker = _SCRIPT_DIR.parent / "config"
_cfg_base_local = _SCRIPT_DIR.parent.parent / "config"
_cfg_base = _cfg_base_docker if (_cfg_base_docker / "assistants.yaml").exists() or \
            (_cfg_base_docker / "assistants.example.yaml").exists() else _cfg_base_local


def _default_config() -> Path:
    for name in ("assistants.yaml", "assistants.example.yaml"):
        p = _cfg_base / name
        if p.exists():
            return p
    return _cfg_base / "assistants.yaml"


def _resolve_system_prompt(entry: dict, config_path: Path) -> str:
    if "system_prompt" in entry:
        return entry["system_prompt"]
    if "system_prompt_file" in entry:
        # Pfad relativ zum Repo-Root (eine Ebene über backend/)
        repo_root = _SCRIPT_DIR.parent.parent
        prompt_path = repo_root / entry["system_prompt_file"]
        if not prompt_path.exists():
            # Docker: Pfad relativ zu /app/
            prompt_path = _SCRIPT_DIR.parent / entry["system_prompt_file"]
        if not prompt_path.exists():
            raise FileNotFoundError(f"system_prompt_file nicht gefunden: {entry['system_prompt_file']}")
        return prompt_path.read_text(encoding="utf-8").strip()
    raise ValueError(f"Assistent '{entry.get('name')}': weder system_prompt noch system_prompt_file angegeben")


async def seed(config_path: Path, dry_run: bool = False) -> None:
    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    entries = data.get("assistants", [])
    if not entries:
        logger.info("Keine Assistenten in %s gefunden.", config_path)
        return

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    inserted = skipped = errors = 0
    async with session_factory() as db:
        for entry in entries:
            name = (entry.get("name") or "").strip()
            if not name:
                logger.warning("Eintrag ohne Name übersprungen.")
                errors += 1
                continue

            existing = (await db.execute(select(Assistant).where(Assistant.name == name))).scalar_one_or_none()
            if existing:
                logger.info("  SKIP  %s (bereits vorhanden, id=%d)", name, existing.id)
                skipped += 1
                continue

            try:
                system_prompt = _resolve_system_prompt(entry, config_path)
            except (FileNotFoundError, ValueError) as e:
                logger.error("  ERROR %s: %s", name, e)
                errors += 1
                continue

            if dry_run:
                logger.info("  DRY   %s → würde angelegt werden", name)
                inserted += 1
                continue

            now = datetime.now(timezone.utc)
            db.add(
                Assistant(
                    name=name,
                    description=(entry.get("description") or "").strip() or None,
                    system_prompt=system_prompt,
                    model=entry.get("model", ""),
                    audience=entry.get("audience", "teacher"),
                    scope=entry.get("scope", "teachers"),
                    status=entry.get("status", "active"),
                    visibility="public",
                    tool_groups=entry.get("tool_groups", []),
                    tags=entry.get("tags") or [],
                    icon=entry.get("icon"),
                    sort_order=int(entry.get("sort_order", 0)),
                    created_by="__seed__",
                    creator_role="admin",
                    created_at=now,
                    updated_at=now,
                )
            )
            logger.info("  OK    %s", name)
            inserted += 1

        if not dry_run:
            await db.commit()

    await engine.dispose()
    action = "würde anlegen" if dry_run else "angelegt"
    logger.info("Fertig: %d %s, %d übersprungen, %d Fehler.", inserted, action, skipped, errors)


def main() -> None:
    parser = argparse.ArgumentParser(description="Assistenten-Seed aus YAML")
    parser.add_argument(
        "--config",
        type=Path,
        default=_default_config(),
        help="Pfad zur YAML-Datei (Standard: config/assistants.yaml oder .example.yaml)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nichts schreiben")
    args = parser.parse_args()

    if not args.config.exists():
        logger.error("Config-Datei nicht gefunden: %s", args.config)
        sys.exit(1)

    logger.info("Seed-Assistenten aus %s ...", args.config)
    asyncio.run(seed(args.config, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
