import logging
import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, delete, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.config import SsoGroupPatterns

logger = logging.getLogger(__name__)

_UMLAUT_TABLE = str.maketrans({
    'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss',
    'Ä': 'ae', 'Ö': 'oe', 'Ü': 'ue',
})


def _normalize_for_slug(value: str) -> str:
    """Normalisiert für Slug-Vergleich: Umlaute ersetzen + lowercase."""
    return value.translate(_UMLAUT_TABLE).lower()


async def _resolve_subject_id(
    db: AsyncSession,
    subject_slug: str,
    aliases: dict[str, str],
) -> Optional[int]:
    """Löst einen aus dem SSO-Token abgeleiteten Wert auf einen Subject-ID auf.

    Reihenfolge:
    1. Direkter Vergleich: normalisierter Wert == normalisierter subject.slug
    2. Alias-Map: normalisierten Wert gegen normalisierte Alias-Keys prüfen,
       dann den Alias-Zielwert wieder als Slug nachschlagen
    """
    from app.db.models import Subject

    normalized = _normalize_for_slug(subject_slug)

    # 1. Direkter case-insensitives Matching
    res = await db.execute(
        select(Subject.id).where(func.lower(Subject.slug) == normalized)
    )
    subject_id = res.scalar_one_or_none()
    if subject_id is not None:
        return subject_id

    # 2. Alias-Map (Keys und Values ebenfalls normalisiert vergleichen)
    normalized_aliases = {_normalize_for_slug(k): _normalize_for_slug(v)
                          for k, v in aliases.items()}
    alias_target = normalized_aliases.get(normalized)
    if alias_target:
        res = await db.execute(
            select(Subject.id).where(func.lower(Subject.slug) == alias_target)
        )
        return res.scalar_one_or_none()

    return None


@dataclass
class ParsedGroup:
    """Repräsentation einer geparsten SSO-Gruppe."""
    sso_group_id: str  # Original-ID aus dem SSO-Token
    type: str  # 'school_class' | 'subject_department' | 'teaching_group'
    name: str  # Anzeigename (aus Capture-Group abgeleitet)
    slug: str  # DB-Slug (normalisiert)
    subject_slug: Optional[str]  # Für subject_department / teaching_group, falls ableitbar


def _sso_id_to_slug(sso_group_id: str) -> str:
    """Normalisiert eine SSO-Gruppen-ID zu einem DB-Slug.

    Beispiele:
      "FS.Mathematik"          → "fs-mathematik"
      "Klasse.8a"              → "klasse-8a"
      "unterricht.8a.Mathematik" → "unterricht-8a-mathematik"
    """
    slug = sso_group_id.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    return slug.strip('-')


def _derive_subject_slug(captured: str) -> Optional[str]:
    """Leitet aus einem Capture-Wert einen Subject-Slug ab.

    Für 'Mathematik' → 'mathematik'
    Für '8a.Mathematik' (teaching_group) → 'mathematik' (letzter Teil)
    Für '8a' (school_class) → None
    """
    parts = captured.split('.')
    if len(parts) >= 2:
        return parts[-1].lower()  # teaching_group: letzter Teil = Fach
    name = parts[0].lower()
    # Nur wenn es wie ein Fachname aussieht (kein reiner Jahrgangscode wie '8a')
    if re.match(r'^[a-z][a-z]+$', name):
        return name
    return None


def parse_sso_groups(
    sso_groups: list[str],
    patterns: SsoGroupPatterns,
) -> list[ParsedGroup]:
    """Parst rohe SSO-Gruppen-IDs gegen die konfigurierten Muster.

    Gruppen ohne Treffer (z.B. activity_group, nicht konfiguriert) werden
    stillschweigend ignoriert.
    """
    result: list[ParsedGroup] = []
    type_patterns: list[tuple[str, str]] = []
    if patterns.subject_department:
        type_patterns.append(("subject_department", patterns.subject_department))
    if patterns.school_class:
        type_patterns.append(("school_class", patterns.school_class))
    if patterns.teaching_group:
        type_patterns.append(("teaching_group", patterns.teaching_group))

    for sso_id in sso_groups:
        for group_type, pattern in type_patterns:
            m = re.match(pattern, sso_id)
            if m:
                captured = m.group(1)
                # Name ableiten
                if group_type == "school_class":
                    name = captured
                    subject_slug = None
                elif group_type == "subject_department":
                    name = captured
                    subject_slug = captured.lower()
                else:  # teaching_group
                    name = captured.replace('.', ' ')
                    subject_slug = _derive_subject_slug(captured)

                result.append(ParsedGroup(
                    sso_group_id=sso_id,
                    type=group_type,
                    name=name,
                    slug=_sso_id_to_slug(sso_id),
                    subject_slug=subject_slug,
                ))
                break  # erste Treffer-Regel gilt
    return result


async def _unique_slug(db: AsyncSession, base_slug: str) -> str:
    """Gibt den Slug zurück, fügt bei Kollision einen Zähler-Suffix an."""
    from app.db.models import Group
    res = await db.execute(select(Group.slug).where(Group.slug == base_slug))
    if res.scalar_one_or_none() is None:
        return base_slug
    # Suffix-Schleife
    for i in range(2, 100):
        candidate = f"{base_slug}-{i}"
        res = await db.execute(select(Group.slug).where(Group.slug == candidate))
        if res.scalar_one_or_none() is None:
            return candidate
    return f"{base_slug}-{id(base_slug)}"  # Notfall-Fallback


async def sync_groups(
    db: AsyncSession,
    pseudonym: str,
    sso_groups: list[str],
    primary_role: str,
    patterns: SsoGroupPatterns,
    aliases: dict[str, str] = {},
) -> None:
    """Synchronisiert Gruppen und Mitgliedschaften für einen einloggenden Nutzer.

    Ablauf:
    1. Parse sso_groups → ParsedGroup-Liste
    2. Upsert Groups (by sso_group_id) — legt fehlende an, aktualisiert Namen
    3. Upsert Mitgliedschaften für alle geparsten Gruppen
    4. Entfernt Mitgliedschaften für Gruppen, die im aktuellen Token nicht mehr vorkommen
    """
    from app.db.models import Group, GroupMembership, Subject

    parsed = parse_sso_groups(sso_groups, patterns)
    if not parsed:
        # Kein Muster passte → alle Mitgliedschaften entfernen (Immediate Mirror)
        await db.execute(
            delete(GroupMembership).where(GroupMembership.pseudonym == pseudonym)
        )
        await db.commit()
        return

    matched_group_ids: list[int] = []

    for pg in parsed:
        # Subject-ID optional nachschlagen
        subject_id: Optional[int] = None
        if pg.subject_slug:
            subject_id = await _resolve_subject_id(db, pg.subject_slug, aliases)
            if subject_id is None:
                logger.warning(
                    "SSO-Gruppe '%s' (Typ '%s'): Fach-Slug '%s' nicht aufgelöst. "
                    "subject_aliases in auth.yaml prüfen.",
                    pg.sso_group_id, pg.type, pg.subject_slug,
                )

        # Groups upsert (by sso_group_id — eindeutige externe ID)
        # Wir suchen zuerst nach sso_group_id, dann nach slug
        res = await db.execute(
            select(Group).where(Group.sso_group_id == pg.sso_group_id)
        )
        group = res.scalar_one_or_none()

        if group is None:
            # Merge-Logik: bei teaching_group-Typen nach manueller TG suchen
            if pg.type == "teaching_group" and subject_id is not None:
                # Manuelle TG mit gleichem Fach, die über eine Klasse erstellt wurde
                # und noch keine sso_group_id hat — adoptieren statt neu anlegen
                from sqlalchemy.orm import joinedload
                res = await db.execute(
                    select(Group)
                    .join(GroupMembership, GroupMembership.group_id == Group.id)
                    .where(
                        GroupMembership.pseudonym == pseudonym,
                        Group.type == "teaching_group",
                        Group.subject_id == subject_id,
                        Group.sso_group_id.is_(None),
                        Group.source_class_group_id.is_not(None),
                    )
                )
                manual_group = res.scalar_one_or_none()
                if manual_group is not None:
                    # SSO-ID übernehmen; Gruppe bleibt erhalten
                    manual_group.sso_group_id = pg.sso_group_id
                    manual_group.name = pg.name  # SSO-Name übernehmen
                    group = manual_group

            if group is None:
                # Neu anlegen; bei Slug-Kollision (selten) Suffix anhängen
                slug = await _unique_slug(db, pg.slug)
                group = Group(
                    name=pg.name,
                    slug=slug,
                    type=pg.type,
                    subject_id=subject_id,
                    sso_group_id=pg.sso_group_id,
                )
                db.add(group)
                await db.flush()  # group.id sofort verfügbar
        else:
            # Vorhandene Gruppe aktualisieren (Name kann sich geändert haben)
            group.name = pg.name
            if subject_id is not None:
                group.subject_id = subject_id

        matched_group_ids.append(group.id)

        # role_in_group nach Gruppentyp
        role_in_group = "teacher" if pg.type == "subject_department" else primary_role

        # Membership upsert
        stmt = (
            pg_insert(GroupMembership)
            .values(
                group_id=group.id,
                pseudonym=pseudonym,
                role_in_group=role_in_group,
            )
            .on_conflict_do_update(
                index_elements=["group_id", "pseudonym"],
                set_={"role_in_group": role_in_group},
            )
        )
        await db.execute(stmt)

    # Immediate Mirror: Mitgliedschaften für nicht mehr enthaltene Gruppen entfernen
    if matched_group_ids:
        await db.execute(
            delete(GroupMembership).where(
                GroupMembership.pseudonym == pseudonym,
                GroupMembership.group_id.not_in(matched_group_ids),
            )
        )
    else:
        await db.execute(
            delete(GroupMembership).where(GroupMembership.pseudonym == pseudonym)
        )

    await db.commit()
