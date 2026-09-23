from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.config import SsoConfig
from app.auth.dependencies import get_current_user, get_sso_config
from app.auth.jwt import JwtPayload
from app.config import settings
from app.calendar.groups import ist_kursstufe
from app.context.grades import parse_class_grade as _parse_grade
from app.db.models import (
    ContextNode,
    Group,
    GroupMembership,
    GroupSourceClass,
    LessonSlot,
    Subject,
    TeacherGroupExclusion,
)
from app.db.session import get_db
from app.planning.calendar import SchoolYearConfig, load_school_year

router = APIRouter(prefix="/groups", tags=["groups"])


class GroupOut(BaseModel):
    id: int
    # Aufgelöst im Backend, nicht in der Oberfläche: 41 Stellen im Frontend zeigen einen
    # Gruppennamen. Käme hier der rohe, wären es 41 Änderungen und 41 Gelegenheiten, eine
    # zu vergessen. `Group.anzeigename` ist `display_name or name`.
    name: str = Field(validation_alias="anzeigename")
    slug: str
    type: str
    subject_id: Optional[int]
    sso_group_id: Optional[str]
    created_at: datetime
    # Was selbst vergeben wurde, oder `null`. `name` oben ist bereits aufgelöst; dieses
    # Feld füllt das Eingabefeld beim Umbenennen und sagt, ob „zurücksetzen" etwas tut.
    display_name: Optional[str] = None
    # Freigabe für die Schüler:innen dieser Gruppe (begrenzter Testbetrieb, Alembic 0063).
    # Immer mitgeliefert, auch wenn der Modus aus ist: Die Oberfläche entscheidet anhand
    # von `student_subjects_opt_in` aus `GET /groups/config`, ob sie darauf hört. Das Feld
    # von der Betriebsart abhängig zu machen hieße, zwei Schalter im Gleichklang zu halten.
    student_visible: bool = False
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class GroupListResponse(BaseModel):
    items: list[GroupOut]


@router.get("", response_model=GroupListResponse)
async def list_groups(
    _: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GroupListResponse:
    """Gibt alle Gruppen zurueck."""
    result = await db.execute(select(Group).order_by(Group.type, Group.name))
    return GroupListResponse(items=list(result.scalars().all()))


class GroupMembershipOut(BaseModel):
    group_id: int
    role_in_group: Optional[str]
    model_config = ConfigDict(from_attributes=True)


class MyGroupOut(GroupOut):
    # Ob die Gruppe zum laufenden Schuljahr gehört — siehe `ist_aktuell`. Nur hier und
    # nicht in `GroupOut`: Für die Gesamtliste aller Schulgruppen wäre die Frage weder
    # sinnvoll noch billig zu beantworten.
    aktuell: bool
    # Das jüngste Schuljahr, aus dem eigene Planung an dieser Gruppe hängt — nur für
    # frühere Gruppen gefüllt und auch dort nur, wenn es etwas zu sagen gibt. Eine
    # geratene Jahreszahl wäre schlechter als keine (dieselbe Regel wie im Archiv).
    letztes_schuljahr: Optional[str] = None


class MyGroupsResponse(BaseModel):
    items: list[MyGroupOut]


def ist_aktuell(gruppe, mit_beleg: set[int], cfg: SchoolYearConfig) -> bool:
    """Ob eine Gruppe zum laufenden Schuljahr gehört.

    Drei Fälle brauchen keine Ableitung:

    * **Kein Unterricht.** Klassen, Fachschaften und Arbeitsgruppen kennen kein
      Schuljahresende in diesem Sinne.
    * **Aus dem Schulkonto.** Für eine Gruppe mit `sso_group_id` ist die Mitgliedschaft
      bereits die Antwort: Der Immediate Mirror entfernt bei jeder Anmeldung, was das Token
      nicht mehr deckt. Steht der Kurs noch im Schulkonto, gibt es ihn. Das trägt zugleich
      den **Kursstufenkurs über zwei Schuljahre** — er hat am ersten Schultag weder Stunden
      noch Jahresplan im neuen Jahr und wäre sonst wochenlang „früher", ohne dass die
      Lehrkraft etwas dagegen tun könnte (der Stundenplan ist noch nicht veröffentlicht).
    * **Gerade erst angelegt.** Sie hat noch nichts, woran man sie erkennen könnte.

    Bleibt die Ableitung für von Hand angelegte und adoptierte Gruppen. Die sind immer an
    eine Klasse gebunden (`POST /groups/teaching` verlangt eine `school_class`) und laufen
    deshalb nie über den Schuljahreswechsel.

    `mit_beleg` sind die Gruppen mit Stunden oder Planung im laufenden Schuljahr —
    ermittelt von `gruppen_mit_beleg`, in **einer** Abfrage für alle.
    """
    if gruppe.type != "teaching_group":
        return True
    if gruppe.sso_group_id:
        return True
    if gruppe.id in mit_beleg:
        return True
    # `astimezone()` vor `date()`: Der Zeitstempel kommt in der Zeitzone der
    # Datenbanksitzung zurück, der Schuljahresbeginn ist ein Kalendertag der Schule. Ohne
    # die Umrechnung entschied die Zeitzone über die Jahresgrenze — eine am ersten
    # Schultag um 00:30 angelegte Gruppe galt als im Vorjahr angelegt. Aufgefallen am
    # 15.09.2026, als der Integrationstest die Grenze mit einem reinen Datum traf.
    return gruppe.created_at.astimezone().date() >= cfg.beginn


async def gruppen_mit_beleg(
    db: AsyncSession, gruppen_ids: list[int], cfg: SchoolYearConfig
) -> set[int]:
    """Welche dieser Gruppen im laufenden Schuljahr Stunden oder Planung haben.

    Zwei Belege, weil sie zu verschiedenen Zeitpunkten entstehen: Der Jahresplan entsteht
    beim ersten Öffnen der Planung, die Stunden erst mit dem Stundenraster. Wer nur auf
    einen schaute, übersähe die halbe Wirklichkeit.
    """
    if not gruppen_ids:
        return set()
    stunden = select(LessonSlot.group_id).where(
        LessonSlot.group_id.in_(gruppen_ids),
        LessonSlot.date.between(cfg.beginn, cfg.ende),
    )
    planung = select(ContextNode.write_scope_group_id).where(
        ContextNode.write_scope_group_id.in_(gruppen_ids),
        ContextNode.schuljahr == cfg.schuljahr,
        ContextNode.status == "active",
    )
    zeilen = await db.execute(stunden.union(planung))
    return {zeile[0] for zeile in zeilen.all()}


async def letztes_schuljahr(
    db: AsyncSession, gruppen_ids: list[int]
) -> dict[int, str]:
    """Das jüngste Schuljahr, aus dem Planung an diesen Gruppen hängt.

    Nur für **frühere** Gruppen gedacht: Dort unterscheidet die Jahreszahl, was der Name
    nicht unterscheidet — „Mathematik 9C" gibt es nach drei Jahren dreimal.

    Die Gruppe selbst weiß nicht, wann sie gelebt hat; ihre Jahrespläne schon. Fehlt die
    Angabe, fehlt sie — geraten wird nicht.
    """
    if not gruppen_ids:
        return {}
    zeilen = await db.execute(
        select(
            ContextNode.write_scope_group_id,
            sa_func.max(ContextNode.schuljahr),
        )
        .where(
            ContextNode.write_scope_group_id.in_(gruppen_ids),
            ContextNode.schuljahr.is_not(None),
            ContextNode.status == "active",
        )
        .group_by(ContextNode.write_scope_group_id)
    )
    return {gid: jahr for gid, jahr in zeilen.all() if jahr}


@router.get("/me", response_model=MyGroupsResponse)
async def list_my_groups(
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MyGroupsResponse:
    """Gibt die Gruppen zurueck, in denen der aktuelle Nutzer Mitglied ist.

    Je Gruppe steht dabei, ob sie zum laufenden Schuljahr gehört. Ohne diese Angabe
    stünden die Unterrichtsgruppen mehrerer Jahre nebeneinander, ohne sich zu
    unterscheiden — der Name trägt kein Jahr, „Mathematik 9C" gibt es dann dreimal.
    """
    stmt = (
        select(Group)
        .join(GroupMembership, GroupMembership.group_id == Group.id)
        .where(GroupMembership.pseudonym == current_user.sub)
        .order_by(Group.type, Group.name)
    )
    result = await db.execute(stmt)
    gruppen = list(result.scalars().all())

    cfg = load_school_year()
    beleg = await gruppen_mit_beleg(
        db, [g.id for g in gruppen if g.type == "teaching_group"], cfg
    )
    aktualitaet = {g.id: ist_aktuell(g, beleg, cfg) for g in gruppen}
    # Nur für die früheren nachschlagen — für die aktuellen sagt die Jahreszahl nichts.
    jahre = await letztes_schuljahr(
        db, [g.id for g in gruppen if not aktualitaet[g.id]]
    )
    return MyGroupsResponse(
        items=[
            # Erst `GroupOut` aus dem ORM-Objekt, dann die Zusätze daneben. Direkt
            # `MyGroupOut.model_validate(gruppe)` schlägt fehl — `aktuell` gibt es am
            # Modell nicht, und die Validierung verlangt es.
            MyGroupOut(
                **GroupOut.model_validate(g, from_attributes=True).model_dump(),
                aktuell=aktualitaet[g.id],
                letztes_schuljahr=jahre.get(g.id),
            )
            for g in gruppen
        ]
    )


class GroupsConfigResponse(BaseModel):
    allow_manual_teaching_groups: bool
    # Begrenzter Testbetrieb (Alembic 0063): Schüler:innen sehen nur freigegebene
    # Unterrichtsgruppen. Die Oberfläche braucht die Auskunft an zwei Stellen — um den
    # Freigabe-Schalter überhaupt zu zeigen (ein Schalter ohne Wirkung ist schlimmer als
    # keiner) und um im Schülerzweig zu filtern.
    student_subjects_opt_in: bool


@router.get("/config", response_model=GroupsConfigResponse)
async def get_groups_config(
    _: JwtPayload = Depends(get_current_user),
    sso_config: SsoConfig = Depends(get_sso_config),
) -> GroupsConfigResponse:
    return GroupsConfigResponse(
        allow_manual_teaching_groups=sso_config.allow_manual_teaching_groups,
        student_subjects_opt_in=settings.student_subjects_opt_in,
    )


class PotentialTeachingGroupItem(BaseModel):
    class_group_id: int
    class_name: str
    class_grade: Optional[int]
    subject_id: int
    subject_name: str
    subject_slug: str
    subject_color: Optional[str]
    subject_icon: Optional[str]


class PotentialTeachingGroupsResponse(BaseModel):
    items: list[PotentialTeachingGroupItem]


@router.get("/teaching/potential", response_model=PotentialTeachingGroupsResponse)
async def list_potential_teaching_groups(
    current_user: JwtPayload = Depends(get_current_user),
    sso_config: SsoConfig = Depends(get_sso_config),
    db: AsyncSession = Depends(get_db),
) -> PotentialTeachingGroupsResponse:
    if not sso_config.allow_manual_teaching_groups:
        return PotentialTeachingGroupsResponse(items=[])
    if "teacher" not in current_user.roles:
        return PotentialTeachingGroupsResponse(items=[])

    pseudonym = current_user.sub

    # Eigene school_class- und subject_department-Gruppen laden
    stmt = (
        select(Group)
        .join(GroupMembership, GroupMembership.group_id == Group.id)
        .where(
            GroupMembership.pseudonym == pseudonym,
            Group.type.in_(["school_class", "subject_department"]),
        )
    )
    result = await db.execute(stmt)
    all_groups = result.scalars().all()

    classes = [g for g in all_groups if g.type == "school_class"]
    dept_subject_ids = {
        g.subject_id for g in all_groups
        if g.type == "subject_department" and g.subject_id is not None
    }

    if not classes or not dept_subject_ids:
        return PotentialTeachingGroupsResponse(items=[])

    # Eigene teaching_groups: (subject_id, Quellklasse) -> bereits vorhanden.
    # Eine Gruppe aus mehreren Klassen erzeugt hier mehrere Paare — richtig so: Für
    # jede beteiligte Klasse ist der Vorschlag „Klasse × Fach" bereits eingelöst.
    stmt = (
        select(Group.subject_id, GroupSourceClass.class_group_id)
        .join(GroupMembership, GroupMembership.group_id == Group.id)
        .join(GroupSourceClass, GroupSourceClass.group_id == Group.id)
        .where(
            GroupMembership.pseudonym == pseudonym,
            Group.type == "teaching_group",
        )
    )
    result = await db.execute(stmt)
    existing_pairs = {(row.subject_id, row.class_group_id) for row in result}

    # Negativliste
    stmt = select(
        TeacherGroupExclusion.class_group_id,
        TeacherGroupExclusion.subject_id,
    ).where(TeacherGroupExclusion.pseudonym == pseudonym)
    result = await db.execute(stmt)
    excluded_pairs = {(row.class_group_id, row.subject_id) for row in result}

    # Subjects laden
    stmt = select(Subject).where(Subject.id.in_(dept_subject_ids))
    result = await db.execute(stmt)
    subjects = {s.id: s for s in result.scalars().all()}

    items: list[PotentialTeachingGroupItem] = []
    for cls in classes:
        # Kursstufe erzeugt keine Vorschläge. Dort gibt es keine Klasse-Fach-Paare mehr:
        # Der Jahrgang zerfällt in Kurse, die quer zu den Klassen liegen — „11 × Chemie"
        # ist dort keine Lerngruppe, sondern ein ganzer Jahrgang. Erkannt an der
        # Bezeichnung, nicht an einer Jahrgangsliste: Sek I trägt immer ein
        # Buchstabensuffix (`5A`…`10D`), die Kursstufe heißt schlicht `11`/`12` (bzw.
        # `12`/`13` in G9, `J1`/`K1`). Das trägt G8 und G9 ohne Konfiguration.
        if ist_kursstufe((cls.name,)):
            continue
        grade = _parse_grade(cls.name)
        for subj_id, subj in subjects.items():
            # Grade-Filter (nur wenn Fach min/max hat UND Jahrgang parsbar)
            if grade is not None and subj.min_grade is not None and subj.max_grade is not None:
                if not (subj.min_grade <= grade <= subj.max_grade):
                    continue
            # Duplikat- und Negativlisten-Filter
            if (subj_id, cls.id) in existing_pairs:
                continue
            if (cls.id, subj_id) in excluded_pairs:
                continue
            items.append(PotentialTeachingGroupItem(
                class_group_id=cls.id,
                class_name=cls.name,
                class_grade=grade,
                subject_id=subj.id,
                subject_name=subj.name,
                subject_slug=subj.slug,
                subject_color=subj.color,
                subject_icon=subj.icon,
            ))

    items.sort(key=lambda x: (
        subjects[x.subject_id].sort_order or 999,
        x.class_name,
    ))
    return PotentialTeachingGroupsResponse(items=items)


class CreateTeachingGroupRequest(BaseModel):
    class_group_id: int
    subject_id: int


class TeachingGroupOut(BaseModel):
    id: int
    name: str = Field(validation_alias="anzeigename")
    slug: str
    subject_id: Optional[int]
    student_visible: bool = False
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


@router.post("/teaching", response_model=TeachingGroupOut, status_code=201)
async def create_teaching_group(
    body: CreateTeachingGroupRequest,
    current_user: JwtPayload = Depends(get_current_user),
    sso_config: SsoConfig = Depends(get_sso_config),
    db: AsyncSession = Depends(get_db),
) -> TeachingGroupOut:
    if not sso_config.allow_manual_teaching_groups:
        raise HTTPException(403, "Manuelles Anlegen von Unterrichtsgruppen ist in dieser Installation deaktiviert")
    if "teacher" not in current_user.roles:
        raise HTTPException(403, "Nur Lehrkräfte können Unterrichtsgruppen anlegen")

    pseudonym = current_user.sub

    # Klasse und Fach validieren
    cls = await db.get(Group, body.class_group_id)
    if cls is None or cls.type != "school_class":
        raise HTTPException(404, "Klasse nicht gefunden")
    subj = await db.get(Subject, body.subject_id)
    if subj is None:
        raise HTTPException(404, "Fach nicht gefunden")

    # Lehrkraft muss in der Klasse sein
    stmt = select(GroupMembership).where(
        GroupMembership.group_id == body.class_group_id,
        GroupMembership.pseudonym == pseudonym,
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(403, "Keine Mitgliedschaft in dieser Klasse")

    # Duplikat verhindern
    stmt = (
        select(Group)
        .join(GroupMembership, GroupMembership.group_id == Group.id)
        .where(
            GroupMembership.pseudonym == pseudonym,
            Group.type == "teaching_group",
            Group.subject_id == body.subject_id,
            Group.id.in_(
                select(GroupSourceClass.group_id).where(
                    GroupSourceClass.class_group_id == body.class_group_id
                )
            ),
        )
    )
    if (await db.execute(stmt)).scalar_one_or_none() is not None:
        raise HTTPException(409, "Unterrichtsgruppe bereits vorhanden")

    # Negativlisten-Eintrag entfernen (falls vorhanden)
    await db.execute(
        delete(TeacherGroupExclusion).where(
            TeacherGroupExclusion.pseudonym == pseudonym,
            TeacherGroupExclusion.class_group_id == body.class_group_id,
            TeacherGroupExclusion.subject_id == body.subject_id,
        )
    )

    # Slug generieren
    base_slug = f"teaching-{subj.slug}-{cls.name.lower()}"
    # Einfache Slug-Generierung - uniqueSlug Funktion nachbilden
    slug = base_slug
    i = 1
    while True:
        stmt = select(Group).where(Group.slug == slug)
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing is None:
            break
        slug = f"{base_slug}-{i}"
        i += 1

    group = Group(
        name=cls.name,
        slug=slug,
        type="teaching_group",
        subject_id=body.subject_id,
        sso_group_id=None,
        # Der manuelle Weg ist „Klasse × Fach" — also der ganze Klassenverband.
        erbt_mitglieder=True,
    )
    db.add(group)
    await db.flush()

    db.add(GroupSourceClass(group_id=group.id, class_group_id=body.class_group_id))

    membership = GroupMembership(
        group_id=group.id,
        pseudonym=pseudonym,
        role_in_group="teacher",
        # `eigen`: Die Mitgliedschaft ist der Nachweis, dass die Gruppe ihr gehört —
        # kein Aufräumlauf darf sie entfernen (Alembic 0068).
        herkunft="eigen",
    )
    db.add(membership)
    await db.commit()
    await db.refresh(group)
    return group


@router.delete("/teaching/{group_id}", status_code=204)
async def delete_teaching_group(
    group_id: int,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    pseudonym = current_user.sub

    # Gruppe laden und prüfen
    group = await db.get(Group, group_id)
    if group is None or group.type != "teaching_group":
        raise HTTPException(404, "Unterrichtsgruppe nicht gefunden")
    if group.sso_group_id is not None:
        raise HTTPException(403, "SSO-Gruppen können nicht manuell gelöscht werden")

    # Eigene Mitgliedschaft prüfen
    stmt = select(GroupMembership).where(
        GroupMembership.group_id == group_id,
        GroupMembership.pseudonym == pseudonym,
        GroupMembership.role_in_group == "teacher",
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(403, "Keine Berechtigung")

    await db.delete(group)
    await db.commit()


class AnzeigenameRequest(BaseModel):
    # Leer oder nur Leerzeichen heißt: zurück auf den Namen aus dem Schulkonto.
    display_name: Optional[str] = None


@router.patch("/teaching/{group_id}/name", response_model=TeachingGroupOut)
async def set_anzeigename(
    group_id: int,
    body: AnzeigenameRequest,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Group:
    """Einen eigenen Namen für die Unterrichtsgruppe setzen oder zurücknehmen.

    **Für alle Unterrichtsgruppen, nicht nur die aus dem Schulkonto.** Der Anlass waren
    zwar SSO-Namen wie `ch2-ks-abi28`, aber eine Ausnahme für adoptierte Gruppen wäre eine
    Regel mehr ohne Gewinn.

    Der Name aus dem Schulkonto (`name`) bleibt unberührt — er ist dessen Eigentum, wird
    bei jedem Login neu geschrieben, und die Stundenplan-Zuordnung rechnet auf ihm.

    Setzen darf, wer in der Gruppe als Lehrkraft eingetragen ist — dieselbe Bedingung, an
    der auch die Jahresplanung hängt. Der Name gilt für **alle**, die die Gruppe sehen;
    bei mehreren Lehrkräften gewinnt die zuletzt gesetzte Fassung.
    """
    from app.planning.permissions import require_group_teacher

    group = await require_group_teacher(group_id, current_user, db)
    gewuenscht = (body.display_name or "").strip()
    group.display_name = gewuenscht or None
    await db.commit()
    await db.refresh(group)
    return group


class SchuelerSichtbarkeitRequest(BaseModel):
    student_visible: bool


@router.patch("/teaching/{group_id}/student-visible", response_model=TeachingGroupOut)
async def set_schueler_sichtbarkeit(
    group_id: int,
    body: SchuelerSichtbarkeitRequest,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Group:
    """Die Gruppe für ihre Schüler:innen freigeben oder die Freigabe zurücknehmen.

    Gedacht für den **begrenzten Testbetrieb**: Nimmt eine Lehrkraft mit einem Teil ihrer
    Lerngruppen teil, sollen ihre Schüler:innen nur die dazugehörigen Fächer sehen. Gelesen
    wird die Freigabe nur bei `STUDENT_SUBJECTS_OPT_IN=true`.

    **Der Endpunkt arbeitet unabhängig von diesem Schalter.** Eine Lehrkraft darf ihre
    Gruppen vorbereiten, auch wenn der Modus gerade aus ist — und beim Abschalten des
    Modus bleiben die Freigaben stehen, statt verloren zu gehen.

    Setzen darf, wer in der Gruppe als Lehrkraft eingetragen ist — dieselbe Bedingung wie
    beim Anzeigenamen und in der Jahresplanung. Die Freigabe gilt für **alle**
    Schüler:innen der Gruppe; bei mehreren Lehrkräften gewinnt die zuletzt gesetzte.
    """
    from app.planning.permissions import require_group_teacher

    group = await require_group_teacher(group_id, current_user, db)
    group.student_visible = body.student_visible
    await db.commit()
    await db.refresh(group)
    return group


class ExclusionOut(BaseModel):
    class_group_id: int
    class_name: str
    subject_id: int
    subject_name: str


@router.get("/exclusions", response_model=list[ExclusionOut])
async def list_exclusions(
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ExclusionOut]:
    stmt = (
        select(
            TeacherGroupExclusion,
            Group.name.label("class_name"),
            Subject.name.label("subject_name"),
        )
        .join(Group, Group.id == TeacherGroupExclusion.class_group_id)
        .join(Subject, Subject.id == TeacherGroupExclusion.subject_id)
        .where(TeacherGroupExclusion.pseudonym == current_user.sub)
        .order_by(Subject.sort_order, Group.name)
    )
    result = await db.execute(stmt)
    return [
        ExclusionOut(
            class_group_id=row.TeacherGroupExclusion.class_group_id,
            class_name=row.class_name,
            subject_id=row.TeacherGroupExclusion.subject_id,
            subject_name=row.subject_name,
        )
        for row in result
    ]


class CreateExclusionRequest(BaseModel):
    class_group_id: int
    subject_id: int


@router.post("/exclusions", status_code=201)
async def add_exclusion(
    body: CreateExclusionRequest,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    excl = TeacherGroupExclusion(
        pseudonym=current_user.sub,
        class_group_id=body.class_group_id,
        subject_id=body.subject_id,
    )
    db.add(excl)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        # Bereits vorhanden = idempotent
        pass
    return {}


@router.delete("/exclusions/{class_group_id}/{subject_id}", status_code=204)
async def remove_exclusion(
    class_group_id: int,
    subject_id: int,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await db.execute(
        delete(TeacherGroupExclusion).where(
            TeacherGroupExclusion.pseudonym == current_user.sub,
            TeacherGroupExclusion.class_group_id == class_group_id,
            TeacherGroupExclusion.subject_id == subject_id,
        )
    )
    await db.commit()
