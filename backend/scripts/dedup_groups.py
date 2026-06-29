#!/usr/bin/env python3
"""
Verschmilzt doppelte Gruppen, die nach Normalisierung identisch sind.

Hintergrund: Vor der case-insensitiven sso_group_id-Behandlung konnten für
dieselbe SSO-Gruppe zwei Zeilen entstehen (z. B. 'FS.Chemie' und 'fs.chemie').
Das führt u. a. dazu, dass die Fachschafts-Prüfung die „falsche" Gruppe trifft.

Duplikat-Schlüssel: (lower(sso_group_id), type, subject_id).
Überlebende je Gruppe: die mit bereits kleingeschriebener sso_group_id, sonst
die mit der kleinsten id. Deren sso_group_id wird auf lowercase normalisiert.
Alle Fremdschlüssel werden auf die Überlebende umgehängt, Mitgliedschaften
zusammengeführt (Konflikte verworfen), die übrigen Gruppen gelöscht.

Verwendung (aus backend/):
    python scripts/dedup_groups.py            # Dry-Run (zeigt nur an)
    python scripts/dedup_groups.py --apply    # tatsächlich ausführen
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Spalten, die auf groups.id verweisen, gruppiert nach Lösch-Regel.
# REPOINT: müssen umgehängt werden (SET NULL würde Daten verlieren bzw. einen
#          CHECK verletzen — z. B. context_nodes.write_scope_group_id bei
#          write_scope='subject'/'group').
_REPOINT_COLUMNS = [
    ("context_nodes", "write_scope_group_id"),
    ("context_nodes", "read_scope_group_id"),
    ("conversations", "group_id"),
    ("assistants", "scope_group_id"),
    ("groups", "source_class_group_id"),
    ("lesson_slots", "group_id"),
    ("slot_plan_snapshots", "group_id"),
    # Nur Surrogat-PK (kein Unique auf der Gruppenspalte) → konfliktfrei umhängbar.
    ("node_engagement", "group_id"),
    ("group_week_patterns", "group_id"),
]
# MERGE: umhängen, aber Konflikte gegen die Überlebende auslassen; Reste werden
#        beim Löschen der Alt-Gruppe per ON DELETE CASCADE entfernt. Nur Tabellen
#        mit zusammengesetztem PK/Unique, der die Gruppenspalte enthält. Schlüssel
#        = die übrigen PK-Spalten (je Gruppe eindeutig).
_MERGE_TABLES = [
    ("group_memberships", "group_id", ["pseudonym"]),
    ("teacher_group_exclusions", "class_group_id", ["pseudonym", "subject_id"]),
]


async def _build_survivor_map(db: AsyncSession) -> dict[int, int]:
    """old_id → survivor_id für alle Duplikat-Sets."""
    rows = (await db.execute(text("""
        WITH ranked AS (
            SELECT id,
                   first_value(id) OVER (
                       PARTITION BY lower(sso_group_id), type, subject_id
                       ORDER BY (sso_group_id = lower(sso_group_id)) DESC, id
                   ) AS survivor_id
            FROM groups
            WHERE sso_group_id IS NOT NULL
        )
        SELECT id, survivor_id FROM ranked WHERE id <> survivor_id
    """))).all()
    return {old: surv for old, surv in rows}


async def dedup(apply: bool) -> None:
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        mapping = await _build_survivor_map(db)
        if not mapping:
            logger.info("Keine Doppelgruppen gefunden — nichts zu tun.")
            await engine.dispose()
            return

        logger.info("%d Doppelgruppe(n) gefunden:", len(mapping))
        for old_id, surv in sorted(mapping.items()):
            info = (await db.execute(text(
                "SELECT g.sso_group_id, g.type, s.sso_group_id "
                "FROM groups g JOIN groups s ON s.id = :surv WHERE g.id = :old"
            ), {"old": old_id, "surv": surv})).first()
            logger.info("  id=%s '%s' (%s) → Überlebende id=%s '%s'",
                        old_id, info[0], info[1], surv, info[2])

        old_ids = list(mapping.keys())

        # 1. Fremdschlüssel umhängen (REPOINT — vollständig)
        for table, col in _REPOINT_COLUMNS:
            n = (await db.execute(text(f"""
                UPDATE {table} t SET {col} = m.survivor_id
                FROM (VALUES {", ".join(f"({o},{s})" for o, s in mapping.items())})
                     AS m(old_id, survivor_id)
                WHERE t.{col} = m.old_id
            """))).rowcount
            if n:
                logger.info("  repoint %s.%s: %d Zeile(n)", table, col, n)

        # 2. MERGE-Tabellen umhängen, Konflikte gegen die Überlebende auslassen
        for table, col, keys in _MERGE_TABLES:
            conflict = " AND ".join(f"x.{k} = t.{k}" for k in keys)
            n = (await db.execute(text(f"""
                UPDATE {table} t SET {col} = m.survivor_id
                FROM (VALUES {", ".join(f"({o},{s})" for o, s in mapping.items())})
                     AS m(old_id, survivor_id)
                WHERE t.{col} = m.old_id
                  AND NOT EXISTS (
                      SELECT 1 FROM {table} x
                      WHERE x.{col} = m.survivor_id AND {conflict}
                  )
            """))).rowcount
            if n:
                logger.info("  merge   %s.%s: %d Zeile(n) umgehängt", table, col, n)

        # 3. sso_group_id der Überlebenden auf lowercase normalisieren
        await db.execute(text(
            "UPDATE groups SET sso_group_id = lower(sso_group_id) "
            "WHERE sso_group_id IS NOT NULL AND sso_group_id <> lower(sso_group_id) "
            "AND id IN (SELECT DISTINCT survivor_id FROM (VALUES "
            + ", ".join(f"({s})" for s in set(mapping.values())) + ") AS v(survivor_id))"
        ))

        # 4. Alt-Gruppen löschen (Rest-Mitgliedschaften etc. via CASCADE)
        deleted = (await db.execute(text(
            f"DELETE FROM groups WHERE id IN ({', '.join(str(i) for i in old_ids)})"
        ))).rowcount

        if apply:
            await db.commit()
            logger.info("Fertig: %d Doppelgruppe(n) verschmolzen und gelöscht.", deleted)
        else:
            await db.rollback()
            logger.info("[DRY-RUN] Würde %d Doppelgruppe(n) verschmelzen. "
                        "Mit --apply ausführen.", deleted)

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Doppelte Gruppen verschmelzen")
    parser.add_argument("--apply", action="store_true",
                        help="Änderungen tatsächlich schreiben (sonst Dry-Run)")
    args = parser.parse_args()
    asyncio.run(dedup(apply=args.apply))


if __name__ == "__main__":
    main()
