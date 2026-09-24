"""Angebote für neue SSO-Unterrichtsgruppen: lesen und beantworten (AP2).

Der Sync hinterlegt, was er gesehen hat (`app/auth/group_sync.py`); hier entscheidet die
Lehrkraft. Drei Antworten: **zuordnen** (die Gruppe gibt es schon), **neu anlegen** oder
**ignorieren**.

**Warum überhaupt gefragt wird:** Aus den SSO-Daten lässt sich nicht bestimmen, ob
`unterricht.9d.ch` die vorhandene Gruppe *Chemie 9D* meint oder eine neue ist —
`ParsedGroup` trägt keine Klassennamen, nur einen Namen als Freitext. Eine falsche
Verschmelzung schiebt zwei Jahrespläne ineinander und ist aus Nutzersicht nicht
rückgängig zu machen.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Conversation,
    Group,
    GroupMembership,
    LessonSlot,
    SsoGroupOffer,
    Subject,
)


@dataclass(frozen=True)
class Kandidat:
    """Eine eigene Gruppe, die das Angebot meinen könnte — mit Beleg."""

    id: int
    name: str
    fach: str | None
    stunden: int
    chats: int

    @property
    def beleg(self) -> str:
        """„Jahresplan, 12 Stunden, 4 Chats" — woran die Lehrkraft sie wiedererkennt.

        ⚠️ **Nicht Zierde.** Ohne den Beleg wählt sie zwischen gleich aussehenden Namen;
        eine falsche Wahl verschmilzt zwei Jahrespläne.
        """
        teile = []
        if self.stunden:
            teile.append(f"{self.stunden} {'Stunde' if self.stunden == 1 else 'Stunden'}")
        if self.chats:
            teile.append(f"{self.chats} {'Chat' if self.chats == 1 else 'Chats'}")
        return " · ".join(teile) if teile else "noch ohne Planung"


@dataclass(frozen=True)
class Angebot:
    id: UUID
    sso_group_id: str
    name: str
    subject_id: int | None
    fach: str | None
    ignoriert: bool


async def lade_angebote(
    db: AsyncSession, pseudonym: str, *, mit_ignorierten: bool = False
) -> list[Angebot]:
    """Die offenen Angebote einer Lehrkraft."""
    stmt = (
        select(SsoGroupOffer, Subject.name)
        .outerjoin(Subject, Subject.id == SsoGroupOffer.subject_id)
        .where(SsoGroupOffer.pseudonym == pseudonym)
        .order_by(SsoGroupOffer.gesehen_am)
    )
    if not mit_ignorierten:
        stmt = stmt.where(SsoGroupOffer.ignoriert_am.is_(None))
    return [
        Angebot(
            id=o.id,
            sso_group_id=o.sso_group_id,
            name=o.name,
            subject_id=o.subject_id,
            fach=fach,
            ignoriert=o.ignoriert_am is not None,
        )
        for o, fach in (await db.execute(stmt)).all()
    ]


async def kandidaten(db: AsyncSession, pseudonym: str) -> list[Kandidat]:
    """Eigene Unterrichtsgruppen **ohne** SSO-Zuordnung, mit Beleg.

    Nur die ohne `sso_group_id`: Eine bereits verknüpfte Gruppe kann nicht zusätzlich
    eine zweite SSO-Gruppe meinen — das wäre der kooperative Fall und ein eigenes Paket.
    """
    stunden = (
        select(LessonSlot.group_id, func.count().label("n"))
        .group_by(LessonSlot.group_id)
        .subquery()
    )
    chats = (
        select(Conversation.group_id, func.count().label("n"))
        .group_by(Conversation.group_id)
        .subquery()
    )
    zeilen = await db.execute(
        select(
            Group.id,
            Group.name,
            Group.display_name,
            Subject.name,
            func.coalesce(stunden.c.n, 0),
            func.coalesce(chats.c.n, 0),
        )
        .join(GroupMembership, GroupMembership.group_id == Group.id)
        .outerjoin(Subject, Subject.id == Group.subject_id)
        .outerjoin(stunden, stunden.c.group_id == Group.id)
        .outerjoin(chats, chats.c.group_id == Group.id)
        .where(
            GroupMembership.pseudonym == pseudonym,
            GroupMembership.role_in_group == "teacher",
            Group.type == "teaching_group",
            Group.sso_group_id.is_(None),
        )
        .order_by(Group.name)
    )
    return [
        Kandidat(id=gid, name=anzeige or name, fach=fach, stunden=n_st, chats=n_ch)
        for gid, name, anzeige, fach, n_st, n_ch in zeilen.all()
    ]


async def _hole(db: AsyncSession, angebot_id: UUID, pseudonym: str) -> SsoGroupOffer:
    offer = await db.get(SsoGroupOffer, angebot_id)
    if offer is None or offer.pseudonym != pseudonym:
        # Bewusst nicht unterschieden: Wem ein fremdes Angebot gehört, geht niemanden an.
        raise LookupError("Angebot nicht gefunden")
    return offer


@dataclass(frozen=True)
class Zuordnungsergebnis:
    group_id: int
    geerbte_entfernt: int


async def ordne_zu(
    db: AsyncSession, angebot_id: UUID, group_id: int, pseudonym: str
) -> Zuordnungsergebnis:
    """Ein Angebot einer vorhandenen Gruppe zuordnen.

    ⚠️ **Geerbte Mitgliedschaften fallen dabei.** Ab jetzt führt das Schulkonto die
    Mitglieder; die Vererbung aus der Klasse ist für SSO-Gruppen abgeschaltet
    (`_erbe_unterrichtsgruppen_der_klasse`). Bliebe das Geerbte stehen, räumte es
    **niemand** mehr auf — auch der Immediate Mirror nicht, der nur `sso` anfasst. Zwei
    Wahrheiten über die Mitgliedschaft, und eine davon eingefroren.

    **Code-Beitritte bleiben.** Sie sind die Entscheidung eines Menschen; sie still zu
    entfernen nähme jemandem den Zugang, den er zu Recht hat. Zurücknehmen kann die
    Lehrkraft sie weiterhin gezielt.
    """
    offer = await _hole(db, angebot_id, pseudonym)
    gruppe = await db.get(Group, group_id)
    if gruppe is None or gruppe.type != "teaching_group":
        raise LookupError("Gruppe nicht gefunden")
    if gruppe.sso_group_id is not None:
        raise ValueError("Diese Gruppe ist bereits mit dem Schulkonto verknüpft.")

    eigene = await db.execute(
        select(GroupMembership).where(
            GroupMembership.group_id == group_id,
            GroupMembership.pseudonym == pseudonym,
            GroupMembership.role_in_group == "teacher",
        )
    )
    if eigene.scalar_one_or_none() is None:
        raise PermissionError("Keine Lehrkraft dieser Gruppe")

    gruppe.sso_group_id = offer.sso_group_id
    gruppe.erbt_mitglieder = False
    entfernt = await db.execute(
        delete(GroupMembership).where(
            GroupMembership.group_id == group_id,
            GroupMembership.herkunft == "geerbt",
        )
    )
    await _loese_auf(db, offer.sso_group_id)
    return Zuordnungsergebnis(group_id=group_id, geerbte_entfernt=entfernt.rowcount or 0)


class FachFehlt(ValueError):
    """Das Angebot trägt kein auflösbares Fach — daraus wird keine Gruppe."""


async def lege_an(db: AsyncSession, angebot_id: UUID, pseudonym: str) -> int:
    """Aus dem Angebot eine neue Gruppe machen.

    ⚠️ **Ohne Fach entsteht hier nichts.** Aus Schülersicht *ist* die Unterrichtsgruppe
    das Fach (CLAUDE.md, Fachbegriff-Tabelle); ohne `subject_id` fällt jede fachbezogene
    Funktion aus — Curriculum-Auflösung, Assistentenauswahl, Fachseite. Die Gruppe sähe
    vollständig aus und wäre es nicht.

    Gefunden am 24.09.2026: `ch-ks-abi28` (Gruppe 27, aus dem Schulkonto am 16.09.
    automatisch angelegt) trug `subject_id = NULL`. In der Jahresplanung stand daraufhin
    „kein Curriculum gefunden“ — eine Auskunft, die zur falschen Suche schickt: Es lag
    nicht am Curriculum.
    """
    offer = await _hole(db, angebot_id, pseudonym)
    if offer.subject_id is None:
        raise FachFehlt(
            f"Zu „{offer.name}“ lässt sich kein Fach bestimmen. "
            "Legen Sie die Gruppe über „Klasse und Fach“ an oder ordnen Sie das Angebot "
            "einer vorhandenen Gruppe zu."
        )
    basis = f"sso-{offer.sso_group_id.replace('.', '-').lower()}"
    slug, lauf = basis, 1
    while (await db.execute(select(Group.id).where(Group.slug == slug))).scalar_one_or_none():
        slug = f"{basis}-{lauf}"
        lauf += 1

    gruppe = Group(
        name=offer.name,
        slug=slug,
        type="teaching_group",
        subject_id=offer.subject_id,
        sso_group_id=offer.sso_group_id,
        # Die Mitglieder kommen aus dem Schulkonto — nicht aus einer Klasse.
        erbt_mitglieder=False,
    )
    db.add(gruppe)
    await db.flush()
    db.add(
        GroupMembership(
            group_id=gruppe.id, pseudonym=pseudonym,
            role_in_group="teacher", herkunft="sso",
        )
    )
    await _loese_auf(db, offer.sso_group_id)
    return gruppe.id


async def ignoriere(db: AsyncSession, angebot_id: UUID, pseudonym: str) -> None:
    """Ablehnen — die Zeile bleibt, damit die Frage nicht wiederkehrt."""
    offer = await _hole(db, angebot_id, pseudonym)
    offer.ignoriert_am = datetime.now(UTC)


async def hebe_ignorieren_auf(db: AsyncSession, angebot_id: UUID, pseudonym: str) -> None:
    """Die Ablehnung zurücknehmen — sonst wäre ein Fehlklick endgültig."""
    offer = await _hole(db, angebot_id, pseudonym)
    offer.ignoriert_am = None


async def _loese_auf(db: AsyncSession, sso_group_id: str) -> int:
    """Alle Angebote zu dieser SSO-Gruppe entfernen — auch die anderer Lehrkräfte.

    ⚠️ **Die Antwort gilt für alle** (Entscheidung F2): Die erste Bestätigung verknüpft,
    die übrigen sehen die Gruppe danach als vorhanden. Bliebe ihr Angebot stehen, führte
    eine zweite Antwort zur Doppelanlage — genau das, was dieser Weg verhindern soll.
    """
    ergebnis = await db.execute(
        delete(SsoGroupOffer).where(SsoGroupOffer.sso_group_id == sso_group_id)
    )
    return ergebnis.rowcount or 0
