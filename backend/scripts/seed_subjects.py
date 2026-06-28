#!/usr/bin/env python3
"""
Fächer aus config/subjects.yaml in die Datenbank einspielen (Upsert).

Verwendung (aus backend/):
    python scripts/seed_subjects.py [--yaml /pfad/zur/subjects.yaml]

Standardpfad: config/subjects.yaml (relativ zum Repo-Root, eine Ebene über backend/)
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import Subject
from app.auth.group_sync import _normalize_for_slug

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Tabellen mit FK subject_id → subjects.id. Beim Prunen wird geprüft, ob ein
# verwaistes Fach hier noch referenziert wird — referenzierte werden nie gelöscht.
_REFERENCING_TABLES = (
    "assistants",
    "conversations",
    "groups",
    "teacher_group_exclusions",
    "context_nodes",
)

_SCRIPT_DIR = Path(__file__).resolve().parent
# Docker: /app/scripts → /app/config/subjects.yaml
# Lokal:  backend/scripts → backend/../config/subjects.yaml
_docker_path = _SCRIPT_DIR.parent / "config" / "subjects.yaml"
_local_path  = _SCRIPT_DIR.parent.parent / "config" / "subjects.yaml"
DEFAULT_YAML = _docker_path if _docker_path.exists() else _local_path


async def _count_references(db: AsyncSession, subject_id: int) -> dict[str, int]:
    """Zählt FK-Referenzen auf ein Fach über alle bekannten Tabellen.

    Tabellennamen sind interne Konstanten (kein User-Input) → f-string unbedenklich;
    subject_id wird als gebundener Parameter übergeben.
    """
    counts: dict[str, int] = {}
    for table in _REFERENCING_TABLES:
        res = await db.execute(
            text(f"SELECT count(*) FROM {table} WHERE subject_id = :sid"),
            {"sid": subject_id},
        )
        n = res.scalar_one()
        if n:
            counts[table] = n
    return counts


async def seed(yaml_path: Path, *, prune: bool = False) -> None:
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    subjects = data.get("subjects", [])
    if not subjects:
        logger.error("Keine Fächer in %s gefunden.", yaml_path)
        sys.exit(1)

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    inserted = updated = deleted = skipped_orphans = 0
    async with session_factory() as db:
        yaml_slugs = {entry["slug"].lower() for entry in subjects}
        for entry in subjects:
            slug = entry["slug"].lower()
            # Fachkürzel normalisieren: leer/fehlend → None, sonst Großschreibung
            raw_code = entry.get("fach_code")
            fach_code = raw_code.strip().upper() if raw_code and raw_code.strip() else None
            # SSO-Aliase normalisieren (lowercase + Umlaute), damit sie dem
            # Matching-Kandidaten in _resolve_subject_id entsprechen.
            sso_aliases = sorted({
                _normalize_for_slug(str(a))
                for a in (entry.get("sso_aliases") or [])
                if a and str(a).strip()
            })
            result = await db.execute(
                select(Subject).where(Subject.slug == slug)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.name = entry["name"]
                existing.fach_code = fach_code
                existing.icon = entry.get("icon")
                existing.color = entry.get("color")
                existing.min_grade = entry.get("min_grade")
                existing.max_grade = entry.get("max_grade")
                existing.sort_order = entry.get("sort_order", 0)
                existing.sso_aliases = sso_aliases
                updated += 1
            else:
                db.add(
                    Subject(
                        slug=slug,
                        name=entry["name"],
                        fach_code=fach_code,
                        icon=entry.get("icon"),
                        color=entry.get("color"),
                        min_grade=entry.get("min_grade"),
                        max_grade=entry.get("max_grade"),
                        sort_order=entry.get("sort_order", 0),
                        sso_aliases=sso_aliases,
                    )
                )
                inserted += 1

        # ── Abgleich: Fächer in der DB, die nicht (mehr) in der YAML stehen ──────
        # subjects.yaml ist die einzige Quelle der Wahrheit. Verwaiste Zeilen (z. B.
        # nach Umbenennung/Konsolidierung) tauchen sonst weiter im Fach-Dropdown auf
        # und können — bei abweichender id — auf einen leeren Bildungsplan zeigen.
        orphans_result = await db.execute(
            select(Subject).where(Subject.slug.notin_(yaml_slugs))
        )
        orphans = orphans_result.scalars().all()
        for orph in orphans:
            refs = await _count_references(db, orph.id)
            if refs:
                ref_str = ", ".join(f"{t}={n}" for t, n in refs.items())
                logger.warning(
                    "Verwaistes Fach '%s' (id=%d) NICHT entfernt — noch referenziert: %s",
                    orph.slug, orph.id, ref_str,
                )
                skipped_orphans += 1
            elif prune:
                await db.delete(orph)
                logger.info(
                    "Verwaistes Fach '%s' (id=%d) entfernt (keine Referenzen).",
                    orph.slug, orph.id,
                )
                deleted += 1
            else:
                logger.warning(
                    "Verwaistes Fach '%s' (id=%d) in DB, nicht in YAML. "
                    "Mit --prune entfernen (nur unreferenzierte werden gelöscht).",
                    orph.slug, orph.id,
                )
                skipped_orphans += 1

        await db.commit()

    await engine.dispose()
    logger.info(
        "Seed abgeschlossen: %d eingefügt, %d aktualisiert, %d entfernt, %d verwaist übersprungen.",
        inserted, updated, deleted, skipped_orphans,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fächer-Seed aus YAML")
    parser.add_argument(
        "--yaml",
        type=Path,
        default=DEFAULT_YAML,
        help=f"Pfad zur subjects.yaml (Standard: {DEFAULT_YAML})",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Fächer löschen, die nicht (mehr) in der YAML stehen "
             "(nur unreferenzierte; referenzierte werden nur gemeldet)",
    )
    args = parser.parse_args()

    if not args.yaml.exists():
        logger.error("YAML-Datei nicht gefunden: %s", args.yaml)
        sys.exit(1)

    asyncio.run(seed(args.yaml, prune=args.prune))


if __name__ == "__main__":
    main()
