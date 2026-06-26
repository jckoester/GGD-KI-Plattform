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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import Subject
from app.auth.group_sync import _normalize_for_slug

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_SCRIPT_DIR = Path(__file__).resolve().parent
# Docker: /app/scripts → /app/config/subjects.yaml
# Lokal:  backend/scripts → backend/../config/subjects.yaml
_docker_path = _SCRIPT_DIR.parent / "config" / "subjects.yaml"
_local_path  = _SCRIPT_DIR.parent.parent / "config" / "subjects.yaml"
DEFAULT_YAML = _docker_path if _docker_path.exists() else _local_path


def _resolve_fach_code(entry: dict) -> str | None:
    """Primärer Fachcode für die (skalare) subjects.fach_code-Spalte.

    Skalares ``fach_code`` direkt; bei Multi-Code (``fach_codes``-Map) der Code des
    untersten Jahrgangsbands. Hinweis: Die skalare Spalte trägt vorerst nur diesen
    Primär-Code — die Laufzeit-Auflösung *beider* Codes folgt mit subjects.fach_codes.
    """
    raw = entry.get("fach_code")
    if raw and str(raw).strip():
        return str(raw).strip().upper()
    codes = entry.get("fach_codes") or {}
    if not codes:
        return None

    def _band_min(band) -> int:
        try:
            return int(str(band).split("-")[0])
        except (ValueError, IndexError):
            return 999

    primary = codes[min(codes, key=_band_min)]
    return str(primary).strip().upper() if primary and str(primary).strip() else None


def _all_fach_codes(entry: dict) -> list[str]:
    """Alle Fachcodes eines Fachs (für die subjects.fach_codes-Spalte).

    Skalares ``fach_code`` → genau dieser Code; Multi-Code (``fach_codes``-Map) →
    alle Codes, dedupliziert, Großschreibung. Gegen diese Liste matcht die
    Cross-Fach-Auflösung (zusätzlich zur skalaren fach_code-Spalte).
    """
    raw = entry.get("fach_code")
    if raw and str(raw).strip():
        return [str(raw).strip().upper()]
    seen: list[str] = []
    for code in (entry.get("fach_codes") or {}).values():
        if code and str(code).strip():
            upper = str(code).strip().upper()
            if upper not in seen:
                seen.append(upper)
    return seen


async def seed(yaml_path: Path) -> None:
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

    inserted = updated = 0
    async with session_factory() as db:
        for entry in subjects:
            slug = entry["slug"].lower()
            # Fachkürzel normalisieren: leer/fehlend → None, sonst Großschreibung.
            # Multi-Code-Fächer (fach_codes) → Primär-Code (unterstes Band) +
            # vollständige Code-Liste für die Cross-Fach-Auflösung.
            fach_code = _resolve_fach_code(entry)
            fach_codes = _all_fach_codes(entry)
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
                existing.fach_codes = fach_codes
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
                        fach_codes=fach_codes,
                    )
                )
                inserted += 1

        await db.commit()

    await engine.dispose()
    logger.info("Seed abgeschlossen: %d eingefügt, %d aktualisiert.", inserted, updated)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fächer-Seed aus YAML")
    parser.add_argument(
        "--yaml",
        type=Path,
        default=DEFAULT_YAML,
        help=f"Pfad zur subjects.yaml (Standard: {DEFAULT_YAML})",
    )
    args = parser.parse_args()

    if not args.yaml.exists():
        logger.error("YAML-Datei nicht gefunden: %s", args.yaml)
        sys.exit(1)

    asyncio.run(seed(args.yaml))


if __name__ == "__main__":
    main()
