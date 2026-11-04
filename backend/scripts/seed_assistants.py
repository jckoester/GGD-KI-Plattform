#!/usr/bin/env python3
"""
Assistenten aus config/assistants.yaml (oder assistants.example.yaml) in die DB anlegen.

Idempotent anhand des Namens: Ein Assistent gleichen Namens wird nicht neu angelegt. Was
ihm **fehlt**, trägt der Seed aus dem Eintrag nach — was gesetzt ist, überschreibt er nie:

- Auslöser-Beispiele (Päckchen C1, 26.10.2026), Rückfälle (27.10.2026), Fächer für
  Operatoren (Päckchen AF);
- seit 0.32.1 auch **Beschreibung, Symbol, Schlagwörter, Fach, Klassenstufen** (nur wenn beide
  Grenzen leer sind), **Vorschlag** (`suggest` auf der Vorgabe `never`, `suggestion_text`) und
  **Dokumente** (nur wenn er keine hat).

⚠️ **Anlass 0.32.1** (Prod, 04.11.2026): Die Assistenten waren aus einer älteren Fassung von
`assistants.example.yaml` entstanden, ohne Fach, Klassenstufen und Vorschlag. Spätere Läufe
übersprangen sie — die Übersicht war unsortiert, Fächer fehlten im Menü, der Vorschlag im Chat
sprang nie an. Ein „leer“ lässt sich von „bewusst leer“ nicht unterscheiden; vor dem ersten
Lauf auf einer eingerichteten Schule deshalb ``--dry-run``: Er nennt je Assistent, was er
nachtragen würde.

Prompt, Modell, Zielgruppe, Freigabe, Status, Sichtbarkeit und Bausteine fasst der Seed bei
einem vorhandenen Assistenten nie an — sie sind Entscheidungen der Schule.

Felder je Eintrag (alle außer `name` und Prompt optional):
`description`, `system_prompt` | `system_prompt_file`, `model`, `audience`, `scope`,
`status`, `visibility`, `tool_groups`, `tags`, `icon`, `sort_order`, `subject` (Slug),
`min_grade`, `max_grade`, `disabled_augmentations`, `documents` (Dateien wie
`system_prompt_file`; als Dokument des Assistenten angehängt), `suggest`, `suggestion_text`,
`trigger_examples`, `trigger_counterexamples`, `fallbacks` (Namen anderer Assistenten),
`operator_faecher` (Fach-Slugs), `bausteine` (Schlüssel aus `app/assistants/bausteine/`; nur beim Anlegen).

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
from app.assistants.bausteine import SCHLUESSEL as BAUSTEIN_SCHLUESSEL
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


async def _operator_faecher(db: AsyncSession, entry: dict) -> list[str]:
    """`operator_faecher` des Eintrags, soweit es die Fächer hier gibt.

    Ein fehlendes Fach wird übergangen, nicht als Fehler gewertet: Die Fächerliste ist
    schulspezifisch (`config/subjects.yaml`), und eine Schule ohne NwT soll den Assistenten
    trotzdem bekommen."""
    slugs = list(dict.fromkeys(str(s).strip().lower() for s in entry.get("operator_faecher") or []))
    if not slugs:
        return []
    vorhanden = set((await db.execute(select(Subject.slug).where(Subject.slug.in_(slugs)))).scalars())
    fehlen = [s for s in slugs if s not in vorhanden]
    if fehlen:
        logger.warning("  Fach für Operatoren übergangen (nicht vorhanden): %s", ", ".join(fehlen))
    return [s for s in slugs if s in vorhanden]


def _bausteine(entry: dict) -> list[str]:
    """`bausteine` des Eintrags, soweit es sie gibt (`app/assistants/bausteine/`).

    **Nur beim Anlegen**, nie nachgetragen: Ein Baustein gehört zum Prompt, und den fasst der
    Seed bei einem vorhandenen Assistenten nicht an (Entscheidung 2 der Landkarte) — ein
    nachgetragener Baustein stünde neben einem Prompt, der dasselbe schon enthält."""
    gewaehlt = list(dict.fromkeys(str(s).strip() for s in entry.get("bausteine") or []))
    fehlen = [s for s in gewaehlt if s not in BAUSTEIN_SCHLUESSEL]
    if fehlen:
        logger.warning("  Baustein übergangen (unbekannt): %s", ", ".join(fehlen))
    return [s for s in gewaehlt if s in BAUSTEIN_SCHLUESSEL]


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


async def _leere_felder_fuellen(db: AsyncSession, existing: Assistant, entry: dict) -> list[str]:
    """Leere Felder eines vorhandenen Assistenten aus dem Eintrag setzen (0.32.1).

    Gibt die Namen der gesetzten Felder zurück — auch im Probelauf, dann auf einer Sitzung, die
    nicht festgeschrieben wird. Ein Fach, das es hier nicht gibt, wird übergangen (wie bei den
    Operatoren-Fächern): Die Fächerliste ist schulspezifisch.
    """
    gesetzt: list[str] = []
    beschreibung = (entry.get("description") or "").strip()
    if beschreibung and not existing.description:
        existing.description = beschreibung
        gesetzt.append("Beschreibung")
    if entry.get("icon") and not existing.icon:
        existing.icon = entry["icon"]
        gesetzt.append("Symbol")
    if entry.get("tags") and not existing.tags:
        existing.tags = list(entry["tags"])
        gesetzt.append("Schlagwörter")
    if entry.get("subject") and existing.subject_id is None:
        fach = (await db.execute(
            select(Subject.id).where(Subject.slug == entry["subject"])
        )).scalar_one_or_none()
        if fach is None:
            logger.warning("  Fach '%s' für %s übergangen (nicht vorhanden)", entry["subject"], existing.name)
        else:
            existing.subject_id = fach
            gesetzt.append("Fach")
    # Beide Grenzen zusammen: Eine allein gesetzte Grenze ist eine Entscheidung, die eine
    # nachgetragene zweite verfälschte („ab 8“ würde zu „8–13“).
    if ((entry.get("min_grade") is not None or entry.get("max_grade") is not None)
            and existing.min_grade is None and existing.max_grade is None):
        existing.min_grade = entry.get("min_grade")
        existing.max_grade = entry.get("max_grade")
        gesetzt.append("Klassenstufen")
    if entry.get("suggest") and existing.suggest == "never":
        existing.suggest = entry["suggest"]
        gesetzt.append("Vorschlag")
    text = (entry.get("suggestion_text") or "").strip()
    if text and not existing.suggestion_text:
        existing.suggestion_text = text
        gesetzt.append("Vorschlagstext")
    if entry.get("documents"):
        vorhanden = (await db.execute(
            select(AssistantDocument.id).where(AssistantDocument.assistant_id == existing.id).limit(1)
        )).first()
        if vorhanden is None:
            for rel in entry["documents"]:
                pfad = _datei(rel)
                inhalt = pfad.read_text(encoding="utf-8")
                db.add(AssistantDocument(
                    assistant_id=existing.id, filename=pfad.name,
                    mime_type="text/markdown" if pfad.suffix == ".md" else "text/plain",
                    size_bytes=len(inhalt.encode("utf-8")), content=inhalt,
                ))
            gesetzt.append("Dokumente")
    return gesetzt


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
            operator_faecher = await _operator_faecher(db, entry)
            if existing:
                # Alles Nachgetragene in einer Zeile je Assistent — und als „ergänzt“ gezählt.
                felder: list[str] = []
                if operator_faecher and not existing.operator_faecher:
                    # Wie Rückfälle: nur nachtragen, wenn noch keine gesetzt sind (Päckchen AF).
                    existing.operator_faecher = operator_faecher
                    felder.append("Fächer für Operatoren " + ", ".join(operator_faecher))
                if entry.get("fallbacks") and not existing.fallbacks:
                    if not dry_run:
                        rueckfaelle.append((existing.id, [str(n) for n in entry["fallbacks"]]))
                    felder.append("Rückfälle " + ", ".join(map(str, entry["fallbacks"])))
                try:
                    felder += await _leere_felder_fuellen(db, existing, entry)
                except FileNotFoundError as e:
                    logger.error("  ERROR %s: %s", name, e)
                    errors += 1
                    continue
                if listen[ausloeser.BEISPIEL] and not await _hat_beispiele(db, existing.id):
                    if not dry_run:
                        await _setze_beispiele(db, existing.id, listen)
                        einzubetten.append(existing.id)
                    felder.append(f"{len(listen[ausloeser.BEISPIEL])} Beispiele, "
                                  f"{len(listen[ausloeser.GEGENBEISPIEL])} Gegenbeispiele")
                if felder:
                    logger.info("  %s %s (id=%d): %s", "DRY  " if dry_run else "NACH ", name,
                                existing.id, ", ".join(felder))
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
                    operator_faecher=operator_faecher,
                    bausteine=_bausteine(entry),
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

        if dry_run:
            # `_leere_felder_fuellen` hat auf der Sitzung gesetzt, um es nennen zu können.
            await db.rollback()
        else:
            await db.commit()
            if einzubetten:
                stand = await ausloeser.einbetten(db, einzubetten)
                logger.info("Beispiele eingebettet: %d ok, %d offen (holt der nächtliche Lauf nach)",
                            stand.ok, stand.fehler)

    if engine is not None:
        await engine.dispose()
    action = "würde anlegen" if dry_run else "angelegt"
    logger.info("Fertig: %d %s, %d %s, %d übersprungen, %d Fehler.",
                inserted, action, nachgetragen,
                "würden ergänzt" if dry_run else "ergänzt", skipped, errors)
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
