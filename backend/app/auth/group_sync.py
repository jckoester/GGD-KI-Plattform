import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, delete, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.config import SsoGroupPatterns


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
            res = await db.execute(
                select(Subject.id).where(Subject.slug == pg.subject_slug)
            )
            subject_id = res.scalar_one_or_none()

        # Groups upsert (by sso_group_id — eindeutige externe ID)
        # Wir suchen zuerst nach sso_group_id, dann nach slug
        res = await db.execute(
            select(Group).where(Group.sso_group_id == pg.sso_group_id)
        )
        group = res.scalar_one_or_none()

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
