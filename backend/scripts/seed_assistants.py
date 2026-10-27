#!/usr/bin/env python3
"""
Assistenten aus config/assistants.yaml (oder assistants.example.yaml) in die DB anlegen.

Idempotent anhand des Namens: Existiert bereits ein Assistent gleichen Namens,
wird er übersprungen — mit **zwei** Ausnahmen: Hat er noch keine Auslöser-Beispiele und
nennt der Eintrag welche, werden sie nachgetragen, samt `suggest` und `suggestion_text`
(Päckchen C1, 26.10.2026); hat er noch keine Rückfälle (`fallbacks`), ebenso diese
(27.10.2026). So bekommt auch ein schon von Hand angelegter Assistent seine
Beispiele; eigene Beispiele werden nie überschrieben.

Felder je Eintrag (alle außer `name` und Prompt optional):
`description`, `system_prompt` | `system_prompt_file`, `model`, `audience`, `scope`,
`status`, `visibility`, `tool_groups`, `tags`, `icon`, `sort_order`, `subject` (Slug),
`min_grade`, `max_grade`, `disabled_augmentations`, `documents` (Dateien wie
`system_prompt_file`; als Dokument des Assistenten angehängt), `suggest`, `suggestion_text`,
`trigger_examples`, `trigger_counterexamples`, `fallbacks` (Namen anderer Assistenten).

Nach dem Anlegen werden die Beispiele eingebettet; scheitert das, holt es der nächtliche
`embedding_backfill.py` nach.

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

from app.assistants import ausloeser
from app.config import settings
from app.db.models import Assistant, AssistantDocument, AssistantTriggerExample, Subject

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


def _datei(rel: str) -> Path:
    """Pfad relativ zum Repo-Root (lokal) bzw. zu /app/ (Docker)."""
    pfad = _SCRIPT_DIR.parent.parent / rel
    if not pfad.exists():
        pfad = _SCRIPT_DIR.parent / rel
    if not pfad.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {rel}")
    return pfad


def _resolve_system_prompt(entry: dict, config_path: Path) -> str:
    if "system_prompt" in entry:
        return entry["system_prompt"]
    if "system_prompt_file" in entry:
        return _datei(entry["system_prompt_file"]).read_text(encoding="utf-8").strip()
    raise ValueError(f"Assistent '{entry.get('name')}': weder system_prompt noch system_prompt_file angegeben")


def _listen(entry: dict) -> dict[str, list[str]]:
    """Beide Beispiel-Listen, bereinigt wie über die API (wirft AusloeserFehler)."""
    return {
        ausloeser.BEISPIEL: ausloeser.bereinige(entry.get("trigger_examples"), ausloeser.BEISPIEL),
        ausloeser.GEGENBEISPIEL: ausloeser.bereinige(
            entry.get("trigger_counterexamples"), ausloeser.GEGENBEISPIEL
        ),
    }


async def _hat_beispiele(db, assistant_id: int) -> bool:
    return (await db.execute(
        select(AssistantTriggerExample.id).where(AssistantTriggerExample.assistant_id == assistant_id).limit(1)
    )).first() is not None


async def _setze_beispiele(db, assistant_id: int, listen: dict[str, list[str]]) -> int:
    neu = 0
    for art, texte in listen.items():
        neu += await ausloeser.setze(db, assistant_id, art, texte)
    return neu


async def seed(config_path: Path, dry_run: bool = False, session_factory=None) -> dict:
    """Legt an bzw. trägt Beispiele nach. ``session_factory`` für Tests; sonst die Konfiguration."""
    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    entries = data.get("assistants", [])
    if not entries:
        logger.info("Keine Assistenten in %s gefunden.", config_path)
        return {"angelegt": 0, "nachgetragen": 0, "uebersprungen": 0, "fehler": 0}

    engine = None
    if session_factory is None:
        engine = create_async_engine(settings.database_url)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    inserted = skipped = errors = nachgetragen = 0
    einzubetten: list[int] = []
    rueckfaelle: list[tuple[int, list[str]]] = []
    async with session_factory() as db:
        for entry in entries:
            name = (entry.get("name") or "").strip()
            if not name:
                logger.warning("Eintrag ohne Name übersprungen.")
                errors += 1
                continue

            try:
                listen = _listen(entry)
            except ausloeser.AusloeserFehler as e:
                logger.error("  ERROR %s: %s", name, e)
                errors += 1
                continue

            existing = (await db.execute(select(Assistant).where(Assistant.name == name))).scalar_one_or_none()
            if existing and entry.get("fallbacks") and not existing.fallbacks:
                # Rückfälle wie Beispiele: nur nachtragen, wenn noch keine gesetzt sind.
                if dry_run:
                    logger.info("  DRY   %s → würde Rückfälle nachtragen", name)
                else:
                    rueckfaelle.append((existing.id, [str(n) for n in entry["fallbacks"]]))
                    logger.info("  NACH  %s (id=%d): Rückfälle %s", name, existing.id,
                                ", ".join(map(str, entry["fallbacks"])))
            if existing:
                if listen[ausloeser.BEISPIEL] and not await _hat_beispiele(db, existing.id):
                    if dry_run:
                        logger.info("  DRY   %s → würde Beispiele nachtragen", name)
                    else:
                        await _setze_beispiele(db, existing.id, listen)
                        if existing.suggest == "never" and entry.get("suggest"):
                            existing.suggest = entry["suggest"]
                        if not existing.suggestion_text and entry.get("suggestion_text"):
                            existing.suggestion_text = entry["suggestion_text"].strip()
                        einzubetten.append(existing.id)
                        logger.info("  NACH  %s (id=%d): %d Beispiele, %d Gegenbeispiele nachgetragen", name,
                                    existing.id, len(listen[ausloeser.BEISPIEL]), len(listen[ausloeser.GEGENBEISPIEL]))
                    nachgetragen += 1
                else:
                    logger.info("  SKIP  %s (bereits vorhanden, id=%d)", name, existing.id)
                    skipped += 1
                continue

            try:
                system_prompt = _resolve_system_prompt(entry, config_path)
                dokumente = [(rel, _datei(rel)) for rel in entry.get("documents") or []]
                subject_id = None
                if entry.get("subject"):
                    subject_id = (await db.execute(
                        select(Subject.id).where(Subject.slug == entry["subject"])
                    )).scalar_one_or_none()
                    if subject_id is None:
                        raise ValueError(f"Fach '{entry['subject']}' nicht gefunden")
            except (FileNotFoundError, ValueError) as e:
                logger.error("  ERROR %s: %s", name, e)
                errors += 1
                continue

            if dry_run:
                logger.info("  DRY   %s → würde angelegt werden", name)
                inserted += 1
                continue

            now = datetime.now(timezone.utc)
            assistant = Assistant(
                    name=name,
                    description=(entry.get("description") or "").strip() or None,
                    system_prompt=system_prompt,
                    # Leer lassen heißt „schulweiter Standard" — der Chat-Flow setzt dann
                    # CHAT_DEFAULT_MODEL ein. Kein Modellname im Seed = wechselfest.
                    model=entry.get("model") or "",
                    audience=entry.get("audience", "teacher"),
                    scope=entry.get("scope", "teachers"),
                    status=entry.get("status", "active"),
                    visibility=entry.get("visibility", "public"),
                    tool_groups=entry.get("tool_groups", []),
                    tags=entry.get("tags") or [],
                    icon=entry.get("icon"),
                    sort_order=int(entry.get("sort_order", 0)),
                    subject_id=subject_id,
                    min_grade=entry.get("min_grade"),
                    max_grade=entry.get("max_grade"),
                    disabled_augmentations=entry.get("disabled_augmentations") or [],
                    image_kinds=[],
                    suggest=entry.get("suggest") or "never",
                    suggestion_text=(entry.get("suggestion_text") or "").strip() or None,
                    fallbacks=[],
                    created_by="__seed__",
                    creator_role="admin",
                    created_at=now,
                    updated_at=now,
            )
            db.add(assistant)
            await db.flush()
            for rel, pfad in dokumente:
                inhalt = pfad.read_text(encoding="utf-8")
                db.add(AssistantDocument(
                    assistant_id=assistant.id, filename=pfad.name,
                    mime_type="text/markdown" if pfad.suffix == ".md" else "text/plain",
                    size_bytes=len(inhalt.encode("utf-8")), content=inhalt,
                ))
            if await _setze_beispiele(db, assistant.id, listen):
                einzubetten.append(assistant.id)
            if entry.get("fallbacks"):
                rueckfaelle.append((assistant.id, [str(n) for n in entry["fallbacks"]]))
            logger.info("  OK    %s%s", name, f" (+{len(dokumente)} Dokument(e))" if dokumente else "")
            inserted += 1

        # Rückfälle erst jetzt: Sie dürfen auf Assistenten derselben Datei zeigen.
        for assistant_id, namen in rueckfaelle:
            ids = []
            for n in namen:
                treffer = list((await db.execute(select(Assistant.id).where(Assistant.name == n))).scalars())
                if len(treffer) == 1 and treffer[0] != assistant_id:
                    ids.append(treffer[0])
                else:
                    logger.warning("  Rückfall '%s' übergangen (%s)", n,
                                   "nicht vorhanden" if not treffer else "nicht eindeutig")
            (await db.get(Assistant, assistant_id)).fallbacks = ids

        if not dry_run:
            await db.commit()
            if einzubetten:
                stand = await ausloeser.einbetten(db, einzubetten)
                logger.info("Beispiele eingebettet: %d ok, %d offen (holt der nächtliche Lauf nach)",
                            stand.ok, stand.fehler)

    if engine is not None:
        await engine.dispose()
    action = "würde anlegen" if dry_run else "angelegt"
    logger.info("Fertig: %d %s, %d mit nachgetragenen Beispielen, %d übersprungen, %d Fehler.",
                inserted, action, nachgetragen, skipped, errors)
    return {"angelegt": inserted, "nachgetragen": nachgetragen, "uebersprungen": skipped, "fehler": errors}


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
