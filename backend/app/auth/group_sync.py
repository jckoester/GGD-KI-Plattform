import logging
import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, delete, func, or_
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


async def _resolve_subject_ids(
    db: AsyncSession,
    subject_slug: str,
) -> list[int]:
    """Löst einen aus dem SSO-Token abgeleiteten Wert auf Subject-IDs auf.

    Case-insensitiv (umlaut-normalisiert ä→ae UND roh kleingeschrieben) gegen:
    1. den Subject-Slug (subjects.slug) — **Direkt-Treffer**, und
    2. die alternativen SSO-Gruppennamen (subjects.sso_aliases) — **Alias-Treffer**.

    Eine Fachschaft kann mehrere Fächer betreuen (z. B. fs.wirtschaft → wirtschaft
    direkt + wbs per Alias). Direkt-Treffer stehen **vorne**, damit Unterrichtsgruppen
    (spezifischer Fachname) eindeutig das gemeinte Fach treffen.
    """
    from app.db.models import Subject

    candidates = list({_normalize_for_slug(subject_slug), subject_slug.lower()})

    direct = await db.execute(
        select(Subject.id)
        .where(func.lower(Subject.slug).in_(candidates))
        .order_by(Subject.id)
    )
    direct_ids = [row[0] for row in direct.all()]

    alias = await db.execute(
        select(Subject.id)
        .where(Subject.sso_aliases.overlap(candidates))
        .order_by(Subject.id)
    )
    seen = set(direct_ids)
    alias_ids = [row[0] for row in alias.all() if row[0] not in seen]

    return direct_ids + alias_ids


async def _resolve_subject_id(
    db: AsyncSession,
    subject_slug: str,
) -> Optional[int]:
    """Einzel-Auflösung: erster (direkt bevorzugter) Treffer oder None."""
    ids = await _resolve_subject_ids(db, subject_slug)
    return ids[0] if ids else None


async def _subject_slugs(db: AsyncSession, subject_ids: list[int]) -> dict[int, str]:
    """Map subject_id → slug für die übergebenen IDs (für eindeutige Gruppen-Slugs)."""
    from app.db.models import Subject
    res = await db.execute(
        select(Subject.id, Subject.slug).where(Subject.id.in_(subject_ids))
    )
    return {row[0]: row[1] for row in res.all()}


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
            # IGNORECASE: IServ liefert kleingeschriebene Accountnamen (fs.mathematik),
            # die Muster sind aber oft mit Großpräfix notiert (^FS\.). Case-insensitiv
            # matchen, damit beide Schreibweisen treffen.
            m = re.match(pattern, sso_id, re.IGNORECASE)
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


async def _upsert_group_and_membership(
    db: AsyncSession,
    pg: ParsedGroup,
    subject_id: Optional[int],
    base_slug: str,
    pseudonym: str,
    primary_role: str,
) -> int:
    """Upsert genau einer Gruppe (für ein Ziel-Fach) + Mitgliedschaft. Gibt group.id.

    Eindeutigkeit einer Gruppe ist das Paar (sso_group_id, subject_id) — eine
    Fachschaft kann mehrere Fächer betreuen und hat dann je Fach eine eigene Gruppe.
    subject_id darf NULL sein (Klasse, Sammelgruppe ohne Fach).
    """
    from app.db.models import Group, GroupMembership

    subject_pred = (
        Group.subject_id == subject_id if subject_id is not None
        else Group.subject_id.is_(None)
    )
    res = await db.execute(
        select(Group).where(Group.sso_group_id == pg.sso_group_id, subject_pred)
    )
    group = res.scalar_one_or_none()

    if group is None:
        # Merge-Logik: bei teaching_group eine manuell (aus Fach+Klasse) erstellte
        # Gruppe ohne sso_group_id adoptieren statt neu anlegen.
        if pg.type == "teaching_group" and subject_id is not None:
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
                manual_group.sso_group_id = pg.sso_group_id
                manual_group.name = pg.name
                group = manual_group

        if group is None:
            slug = await _unique_slug(db, base_slug)
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
        # Vorhandene Gruppe: Name kann sich geändert haben (subject_id ist Lookup-Teil)
        group.name = pg.name

    role_in_group = "teacher" if pg.type == "subject_department" else primary_role
    await db.execute(
        pg_insert(GroupMembership)
        .values(group_id=group.id, pseudonym=pseudonym, role_in_group=role_in_group)
        .on_conflict_do_update(
            index_elements=["group_id", "pseudonym"],
            set_={"role_in_group": role_in_group},
        )
    )
    return group.id


async def sync_groups(
    db: AsyncSession,
    pseudonym: str,
    sso_groups: list[str],
    primary_role: str,
    patterns: SsoGroupPatterns,
) -> None:
    """Synchronisiert Gruppen und Mitgliedschaften für einen einloggenden Nutzer.

    Eine Fachschaft (subject_department) kann mehrere Fächer betreuen (z. B.
    fs.wirtschaft → wirtschaft + wbs); dann wird je Fach eine eigene Gruppe geführt
    (Slug `<fachschaft>-<fachslug>`). Unterrichtsgruppen treffen genau ein Fach
    (direkter Slug bevorzugt), Klassen kein Fach. Immediate Mirror entfernt
    Mitgliedschaften, die im aktuellen Token nicht mehr vorkommen.
    """
    from app.db.models import GroupMembership

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
        # Ziel-Fächer + Gruppen-Slug je Fach bestimmen
        targets: list[tuple[Optional[int], str]]
        if pg.type == "subject_department" and pg.subject_slug:
            subject_ids = await _resolve_subject_ids(db, pg.subject_slug)
            if not subject_ids:
                logger.warning(
                    "SSO-Gruppe '%s' (subject_department): Fach-Slug '%s' nicht aufgelöst. "
                    "Fach + ggf. sso_aliases in config/subjects.yaml prüfen.",
                    pg.sso_group_id, pg.subject_slug,
                )
                targets = [(None, pg.slug)]
            elif len(subject_ids) == 1:
                targets = [(subject_ids[0], pg.slug)]
            else:
                # Mehrere Fächer je Fachschaft → je Fach eine Gruppe mit eindeutigem Slug
                slugs = await _subject_slugs(db, subject_ids)
                targets = [(sid, f"{pg.slug}-{slugs.get(sid, sid)}") for sid in subject_ids]
        elif pg.type == "teaching_group" and pg.subject_slug:
            subject_id = await _resolve_subject_id(db, pg.subject_slug)
            if subject_id is None:
                logger.warning(
                    "SSO-Gruppe '%s' (teaching_group): Fach-Slug '%s' nicht aufgelöst. "
                    "Fach + ggf. sso_aliases in config/subjects.yaml prüfen.",
                    pg.sso_group_id, pg.subject_slug,
                )
            targets = [(subject_id, pg.slug)]
        else:
            targets = [(None, pg.slug)]

        for subject_id, base_slug in targets:
            gid = await _upsert_group_and_membership(
                db, pg, subject_id, base_slug, pseudonym, primary_role
            )
            matched_group_ids.append(gid)

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
