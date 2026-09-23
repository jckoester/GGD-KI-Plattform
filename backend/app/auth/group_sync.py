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


def _unterrichtsgruppe_lesen(
    treffer: re.Match, sso_id: str, captured: str
) -> tuple[str, Optional[str]]:
    """Anzeigename und Fachkürzel einer Unterrichtsgruppe aus dem Treffer.

    **Warum es hier eine Wahl gibt.** Die ursprüngliche Ableitung riet das Fach aus dem
    letzten punktgetrennten Segment (`unterricht.8a.mathematik` → `mathematik`). Das
    unterstellt, dass die Schule ihre Gruppen frei benennen kann. Wer sie aus dem
    Stundenplan übernimmt, kann das nicht: `unterricht.ch2-ks-11` hat keinen Punkt, das
    Raten scheitert, und die Gruppe landet **ohne Fach** in der Datenbank — sichtbar im
    Profil, aber unter keinem Fach (aufgetreten in Produktion, 13.09.2026).

    Mit `(?P<fach>…)` im Muster sagt die Konfiguration, wo das Fach steht, statt dass die
    Plattform es errät. `(?P<bezeichnung>…)` tut dasselbe für den Anzeigenamen.

    Der Rückfall ohne benannte Gruppen ist das alte Verhalten — unverändert, damit
    bestehende Konfigurationen weiterlaufen.
    """
    benannt = treffer.groupdict()

    if "bezeichnung" in benannt and benannt["bezeichnung"]:
        name = benannt["bezeichnung"]
    elif benannt:
        # Benannte Gruppen im Spiel, aber keine `bezeichnung`: Gruppe 1 ist dann die
        # erste *benannte* Gruppe und meist zu schmal (bei `(?P<fach>[a-z]+)` bliebe
        # als Name „ch" übrig). Die volle Kennung ist unschön, aber nie falsch.
        name = sso_id
    else:
        name = captured.replace(".", " ")

    if "fach" in benannt:
        fach = (benannt["fach"] or "").lower() or None
    else:
        fach = _derive_subject_slug(captured)

    return name, fach


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
                    name, subject_slug = _unterrichtsgruppe_lesen(m, sso_id, captured)

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
    from app.db.models import Group, GroupMembership, GroupSourceClass

    # sso_group_id normalisiert (lowercase) als kanonischer Schlüssel: verhindert
    # Doppelgruppen, wenn der Provider die Schreibweise ändert (z. B. 'FS.Chemie'
    # vs 'fs.chemie'). Lookup case-insensitiv, gespeichert wird stets lowercase.
    sso_id_norm = pg.sso_group_id.lower()
    subject_pred = (
        Group.subject_id == subject_id if subject_id is not None
        else Group.subject_id.is_(None)
    )
    res = await db.execute(
        select(Group).where(
            func.lower(Group.sso_group_id) == sso_id_norm, subject_pred
        )
    )
    # .first() statt .scalar_one_or_none(): toleriert Alt-Bestände mit (noch nicht
    # deduplizierten) Doppelgruppen, bis dedup_groups.py gelaufen ist.
    group = res.scalars().first()

    if group is None:
        # Dieselbe SSO-Gruppe, bisher **ohne** Fach: nachträglich zuordnen statt eine
        # zweite Zeile anzulegen.
        #
        # Der Fall entsteht beim Nachziehen der Konfiguration: Solange das Muster kein
        # `(?P<fach>…)` trug, landeten Unterrichtsgruppen aus dem Stundenplan ohne Fach
        # in der Datenbank. Ohne diese Adoption ergäbe der erste Login danach ein Paar —
        # eine verwaiste Zeile ohne Fach und eine neue mit Slug-Suffix `-2`. `dedup_groups`
        # räumt das nicht auf, weil `subject_id` Teil seines Schlüssels ist.
        #
        # Nur für Unterrichtsgruppen: Eine Fachschaft kann mehrere Fächer betreuen, dort
        # wäre „die Zeile ohne Fach ist dieselbe" falsch.
        if pg.type == "teaching_group" and subject_id is not None:
            res = await db.execute(
                select(Group).where(
                    func.lower(Group.sso_group_id) == sso_id_norm,
                    Group.subject_id.is_(None),
                    Group.type == "teaching_group",
                )
            )
            ohne_fach = res.scalars().first()
            if ohne_fach is not None:
                logger.info(
                    "SSO-Gruppe '%s': Fach nachgetragen (subject_id=%s) statt Doppelanlage.",
                    pg.sso_group_id, subject_id,
                )
                ohne_fach.subject_id = subject_id
                ohne_fach.name = pg.name
                group = ohne_fach

        # Merge-Logik: bei teaching_group eine manuell (aus Fach+Klasse) erstellte
        # Gruppe ohne sso_group_id adoptieren statt neu anlegen.
        if group is None and pg.type == "teaching_group" and subject_id is not None:
            res = await db.execute(
                select(Group)
                .join(GroupMembership, GroupMembership.group_id == Group.id)
                .where(
                    GroupMembership.pseudonym == pseudonym,
                    Group.type == "teaching_group",
                    Group.subject_id == subject_id,
                    Group.sso_group_id.is_(None),
                    Group.id.in_(select(GroupSourceClass.group_id)),
                )
            )
            manual_group = res.scalar_one_or_none()
            if manual_group is not None:
                manual_group.sso_group_id = sso_id_norm
                manual_group.name = pg.name
                group = manual_group

        if group is None:
            slug = await _unique_slug(db, base_slug)
            group = Group(
                name=pg.name,
                slug=slug,
                type=pg.type,
                subject_id=subject_id,
                sso_group_id=sso_id_norm,
            )
            db.add(group)
            await db.flush()  # group.id sofort verfügbar
    else:
        # Vorhandene Gruppe: Name kann sich geändert haben (subject_id ist Lookup-Teil).
        # sso_group_id bei Bedarf auf lowercase normalisieren (heilt Alt-Schreibweisen).
        if group.sso_group_id != sso_id_norm:
            group.sso_group_id = sso_id_norm
        group.name = pg.name

    role_in_group = "teacher" if pg.type == "subject_department" else primary_role
    await db.execute(
        pg_insert(GroupMembership)
        .values(
            group_id=group.id,
            pseudonym=pseudonym,
            role_in_group=role_in_group,
            herkunft="sso",
        )
        .on_conflict_do_update(
            index_elements=["group_id", "pseudonym"],
            # Auch die Herkunft nachziehen: Wer erst per Code beitrat und später vom
            # Provider genannt wird, gehört ab jetzt dem Spiegel — sonst bliebe eine
            # Mitgliedschaft stehen, die das Token nicht mehr deckt.
            set_={"role_in_group": role_in_group, "herkunft": "sso"},
        )
    )
    return group.id


async def _spiegle_mitgliedschaften(
    db: AsyncSession, pseudonym: str, behalten: list[int]
) -> None:
    """Immediate Mirror: entfernt Mitgliedschaften, die das Token nicht mehr deckt.

    **Nur für Gruppen mit `sso_group_id`.** Eine Gruppe ohne SSO-Entsprechung steht in
    keinem Token und wäre sonst bei *jedem* Login fällig — auch die, die eine Lehrkraft
    sich gerade erst aus einem Vorschlag angelegt hat. Nachgemessen am 13.09.2026: Sie
    verlor dabei ihre **eigene** Mitgliedschaft, nicht nur die von Hand eingetragenen
    Mitglieder; die Gruppe war nach dem nächsten Login leer und nur noch im Archiv
    erreichbar.

    Was keine SSO-Entsprechung hat, wird von Hand oder abgeleitet gepflegt — der Spiegel
    ist dafür nicht zuständig. Er ist es weiterhin für alles, was aus dem Token kommt:
    Fällt eine Fachschaft weg, fällt die Mitgliedschaft.
    """
    from app.db.models import Group, GroupMembership

    aus_dem_sso = select(Group.id).where(Group.sso_group_id.is_not(None))
    bedingungen = [
        GroupMembership.pseudonym == pseudonym,
        GroupMembership.group_id.in_(aus_dem_sso),
    ]
    if behalten:
        bedingungen.append(GroupMembership.group_id.not_in(behalten))
    await db.execute(delete(GroupMembership).where(*bedingungen))


async def _erbe_unterrichtsgruppen_der_klasse(
    db: AsyncSession, pseudonym: str, klassen_ids: list[int], primary_role: str
) -> None:
    """Schüler:innen erben die Unterrichtsgruppen, die aus ihrer Klasse abgeleitet sind.

    **Die zweite Hälfte der Adoption.** Bestätigt eine Lehrkraft den Vorschlag „Klasse 8a
    × Mathematik", entsteht eine Unterrichtsgruppe mit einem Eintrag in
    `group_source_classes` auf die 8a — bisher aber mit der Lehrkraft als einzigem
    Mitglied. Für Schüler:innen blieb sie
    unsichtbar, obwohl im Datenmodell steht, woher sie kommt. Das war der Grund, warum
    ein im Klassenverband unterrichtetes Fach trotzdem eine eigene SSO-Gruppe brauchte —
    also genau die Verwaltungsarbeit, die die Ableitung ersparen sollte.

    **Nur Schüler:innen.** Rollenblind gedacht zöge die Regel jede Lehrkraft, die in der
    8a ist, in *jede* abgeleitete Gruppe dieser Klasse — die Klassenleitung säße in
    „Mathe 8a", ohne das Fach zu unterrichten. Lehrkräfte kommen ausschließlich über
    ihre eigene Adoption hinein.

    **Nur Gruppen ohne `sso_group_id`.** Gibt es zu einer Unterrichtsgruppe eine
    SSO-Entsprechung, ist deren Mitgliederliste maßgeblich; abzuleiten hieße, Leute
    hineinzuschreiben, die der Provider nicht nennt.

    Die Mitgliedschaft ist **abgeleitet**, nicht von Hand gesetzt: Wer die Klasse
    verlässt, verliert sie beim nächsten Login wieder. Diese Bereinigung macht der
    Immediate Mirror nicht — er fasst Gruppen ohne `sso_group_id` bewusst nicht an —,
    also steht sie hier.
    """
    if primary_role != "student":
        return

    from app.db.models import Group, GroupMembership, GroupSourceClass

    abgeleitet: list[int] = []
    if klassen_ids:
        # ⚠️ **Geerbt wird nur aus einer einzelnen Klasse** (Entscheidung Jan,
        # 23.09.2026). Steht im Stundenplan eine Gruppe über **mehreren** Klassen
        # (`NWT_10A10B10C`), ist sie per Konstruktion eine **Auswahl** aus diesen
        # Klassen — sonst würde sie je Klasse unterrichtet. Alle drei Klassen
        # hineinzuschreiben gäbe Schüler:innen Zugang zu einer Gruppe, in der sie nicht
        # sind: falsche Assistenten-Freigaben, falscher Unterrichtskontext. Solche
        # Gruppen füllen sich über einen Beitrittscode oder über eine SSO-Gruppe.
        #
        # Der Preis: Zwei kleine Klassen, die *vollständig* gemeinsam unterrichtet
        # werden, brauchen ebenfalls den Code. Das ist unbequem — die Gegenrichtung
        # wäre ein stiller Zugriffsfehler, und der ist teurer.
        einzelklassig = (
            select(GroupSourceClass.group_id)
            .group_by(GroupSourceClass.group_id)
            .having(func.count() == 1)
        )
        abgeleitet = list((await db.execute(
            select(Group.id)
            .join(GroupSourceClass, GroupSourceClass.group_id == Group.id)
            .where(
                Group.type == "teaching_group",
                Group.sso_group_id.is_(None),
                GroupSourceClass.class_group_id.in_(klassen_ids),
                Group.id.in_(einzelklassig),
            )
            .distinct()
        )).scalars())

    for gid in abgeleitet:
        await db.execute(
            pg_insert(GroupMembership)
            .values(
                group_id=gid,
                pseudonym=pseudonym,
                role_in_group="student",
                herkunft="geerbt",
            )
            # `do_nothing`, nicht `do_update`: Wer schon per Code beigetreten ist oder
            # von Hand eingetragen wurde, behält seine Herkunft — sonst würde die
            # Ableitung sie überschreiben und der Abgang unten sie anschließend löschen.
            .on_conflict_do_nothing(index_elements=["group_id", "pseudonym"])
        )

    # Abgang: geerbte Mitgliedschaften, deren Quellklasse nicht mehr passt.
    #
    # Bewusst **ohne** die Einzelklassen-Bedingung von oben: Bekommt eine bisher
    # einklassige Gruppe eine zweite Quellklasse, wird sie zur Teilgruppe und erbt nicht
    # mehr — die vorher geerbten Mitgliedschaften müssen dann fallen. Mit der Bedingung
    # hier stünden sie für immer drin, weil die Gruppe nie wieder in `abgeleitet` käme.
    veraltet = select(Group.id).where(
        Group.type == "teaching_group",
        Group.sso_group_id.is_(None),
        Group.id.in_(select(GroupSourceClass.group_id)),
    )
    if abgeleitet:
        veraltet = veraltet.where(Group.id.not_in(abgeleitet))
    await db.execute(
        delete(GroupMembership).where(
            GroupMembership.pseudonym == pseudonym,
            # ⚠️ **Nur `geerbt`, nicht mehr `role_in_group == 'student'`.** Bis Alembic
            # 0068 war beides gleichbedeutend; mit dem Beitrittscode ist es das nicht
            # mehr. Nach der Rolle zu löschen risse jede:n Code-Beitretende:n aus einer
            # Gruppe, die zufällig auch eine Quellklasse hat — also genau die Nachzügler,
            # für die es den Code gibt.
            GroupMembership.herkunft == "geerbt",
            GroupMembership.group_id.in_(veraltet),
        )
    )


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
        # Kein Muster passte → alle SSO-gestützten Mitgliedschaften entfernen. Die
        # Vererbung muss **auch hier** laufen: Ohne Klasse gibt es nichts zu erben, und
        # was zuvor geerbt wurde, gehört weg. Der erste Entwurf kehrte an dieser Stelle
        # zurück — eine Schülerin ohne Klassen behielt ihre geerbten Gruppen für immer.
        await _spiegle_mitgliedschaften(db, pseudonym, behalten=[])
        await _erbe_unterrichtsgruppen_der_klasse(db, pseudonym, [], primary_role)
        await db.commit()
        return

    matched_group_ids: list[int] = []
    klassen_ids: list[int] = []

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
                # Rückfall auf das Stundenplan-Vokabular. Wer seine Unterrichtsgruppen
                # aus dem Stundenplan übernimmt, hat dort dessen Kürzel stehen (`ch2`,
                # `m`) — und dafür führt `subjects.yaml` bereits `untis_codes`. Sie in
                # `sso_aliases` zu wiederholen wäre ein **viertes** Vokabular mit
                # demselben Inhalt; der Auflöser schneidet nebenbei die Kursziffer ab
                # (`ch2` → `CH`).
                from app.calendar.groups import resolve_subject

                subject_id = await resolve_subject(db, pg.subject_slug)
            if subject_id is None:
                logger.warning(
                    "SSO-Gruppe '%s' (teaching_group): Fach '%s' nicht aufgelöst — weder "
                    "über Slug/sso_aliases noch über untis_codes/fach_code. "
                    "config/subjects.yaml prüfen.",
                    pg.sso_group_id, pg.subject_slug,
                )
            targets = [(subject_id, pg.slug)]
        else:
            if pg.type == "teaching_group":
                # Eine Unterrichtsgruppe ohne Fach ist kein Randfall, sondern eine
                # Gruppe, die unter keinem Fach erscheinen kann — sie steht dann nur im
                # Profil, und niemand sieht, warum. Genau so lief es bis 13.09.2026
                # still: Die Warnung darüber greift erst, wenn ein Fach-Slug abgeleitet
                # *und* nicht aufgelöst wurde; bei „gar nicht abgeleitet" schwieg alles.
                logger.warning(
                    "SSO-Gruppe '%s' (teaching_group): kein Fach ableitbar. Die Gruppe "
                    "erscheint unter keinem Fach. Muster in config/auth.yaml um eine "
                    "benannte Gruppe (?P<fach>…) ergänzen.",
                    pg.sso_group_id,
                )
            targets = [(None, pg.slug)]

        for subject_id, base_slug in targets:
            gid = await _upsert_group_and_membership(
                db, pg, subject_id, base_slug, pseudonym, primary_role
            )
            matched_group_ids.append(gid)
            if pg.type == "school_class":
                klassen_ids.append(gid)

    await _spiegle_mitgliedschaften(db, pseudonym, behalten=matched_group_ids)
    await _erbe_unterrichtsgruppen_der_klasse(db, pseudonym, klassen_ids, primary_role)
    await db.commit()
