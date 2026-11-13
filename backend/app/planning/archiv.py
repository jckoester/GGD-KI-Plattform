"""Archiv der Planung (0.42, Päckchen AO; Plan F2, F3, F11, F12).

Das Archiv zeigt Gruppen, die **nicht im Menü „Planung“** stehen, mit ihren Einheiten und
Stunden — immer lesend. Zwei Wege hinein, dieselben wie bei `zugang_zur_stunde`:

* **Mitgliedschaft** als Lehrkraft in einer Gruppe, die nicht mehr aktuell ist
  (`ist_aktuell`, Fall 4a) → alle Einheiten und Stunden der Gruppe.
* **Eigentum** an Einheiten oder Stunden einer Gruppe, in der man nicht (mehr) Lehrkraft ist
  (Fall 4b) → nur die eigenen. Eine fremde Einheit erscheint, wenn eine eigene Stunde in ihr
  steht — mit Titel, aber nur den eigenen Stunden (den Titel zeigt die Entwurfsansicht der
  Stunde ohnehin).

Gezeigt wird Aktives **und** vom Lebenszyklus Archiviertes (F11): Stunden und Einheiten laufen
zum Schuljahresende ab. Der Jahresplan selbst zählt nicht — er entsteht beim Öffnen des Planers
und trägt nichts, was man im Archiv sucht.

⚠️ **Der Filter ist die Zugriffsregel** — wie bei `GET /planning/groups`. Kein Admin-Sonderfall.
Eine feste Zahl von Abfragen, nicht eine je Gruppe.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import JwtPayload
from app.auth.vorschau import eigenes_zaehlt, mitglied
from app.db.models import ContextEdge, ContextNode, Group, GroupMembership, LessonSlot, Subject
from app.groups.aktualitaet import (
    gruppen_mit_beleg,
    gruppen_mit_quellklasse,
    ist_aktuell,
    schuljahr_des_knotens,
)
from app.planning.calendar import load_school_year

EINHEIT = "unterrichtseinheit"
STUNDE = "unterrichtsstunde"
LESBAR: tuple[str, ...] = ("active", "archived")

MITGLIED = "mitglied"
EIGENTUM = "eigentum"


@dataclass
class ArchivGruppe:
    gruppe: Group
    fach: Subject | None
    zugang: str
    schuljahr: str | None = None
    einheiten: int = 0
    stunden: int = 0


@dataclass
class ArchivStunde:
    id: UUID
    titel: str
    stundenziel: str | None
    datum: date | None
    nachbereitet: bool
    archiviert: bool
    # Der Termin, an dem die Stunde hängt — None heißt „ohne Termin“ (0.42.3, Einplanen).
    slot_id: UUID | None = None


@dataclass
class ArchivEinheit:
    id: UUID
    titel: str
    farbe: int
    schuljahr: str | None
    archiviert: bool
    stunden: list[ArchivStunde] = field(default_factory=list)


@dataclass
class ArchivInhalt:
    gruppe: Group
    fach: Subject | None
    zugang: str
    einheiten: list[ArchivEinheit]
    ohne_einheit: list[ArchivStunde]


def _eigene_gruppen_ids(pseudonym: str):
    """Gruppen, an denen eigene Einheiten oder Stunden hängen (lesbar)."""
    return (
        sa.select(ContextNode.write_scope_group_id)
        .where(
            ContextNode.owner_pseudonym == pseudonym,
            ContextNode.content_type.in_((EINHEIT, STUNDE)),
            ContextNode.status.in_(LESBAR),
            ContextNode.write_scope_group_id.is_not(None),
        )
        .distinct()
    )


async def _lehrkraft_gruppen(db: AsyncSession, user: JwtPayload) -> set[int]:
    zeilen = await db.execute(
        sa.select(GroupMembership.group_id).where(mitglied(user.sub, "teacher"))
    )
    return {z[0] for z in zeilen.all()}


async def archiv_gruppen(db: AsyncSession, user: JwtPayload) -> list[ArchivGruppe]:
    """Die Gruppen des Archivs mit Zugang, Schuljahr und Zahl der Einheiten und Stunden."""
    cfg = load_school_year()
    lehrkraft = await _lehrkraft_gruppen(db, user)
    eigene: set[int] = set()
    if eigenes_zaehlt(user.sub):
        eigene = {z[0] for z in (await db.execute(_eigene_gruppen_ids(user.sub))).all()}

    kandidaten = lehrkraft | eigene
    if not kandidaten:
        return []
    paare = (
        await db.execute(
            sa.select(Group, Subject)
            .outerjoin(Subject, Subject.id == Group.subject_id)
            .where(Group.id.in_(kandidaten), Group.type == "teaching_group")
        )
    ).all()
    ids = [g.id for g, _ in paare]
    beleg = await gruppen_mit_beleg(db, ids, cfg)
    quellklasse = await gruppen_mit_quellklasse(db, ids)

    archiv: dict[int, ArchivGruppe] = {}
    for g, f in paare:
        if g.id in lehrkraft:
            if ist_aktuell(g, beleg, cfg, quellklasse):
                continue  # steht im Menü
            archiv[g.id] = ArchivGruppe(g, f, MITGLIED)
        else:
            archiv[g.id] = ArchivGruppe(g, f, EIGENTUM)
    if not archiv:
        return []

    # Zahlen und Schuljahr in einer Abfrage — der Zugang steckt in der Bedingung.
    mitglied_ids = [gid for gid, a in archiv.items() if a.zugang == MITGLIED]
    eigentum_ids = [gid for gid, a in archiv.items() if a.zugang == EIGENTUM]
    zeilen = await db.execute(
        sa.select(
            ContextNode.write_scope_group_id,
            ContextNode.content_type,
            sa.func.count(),
            sa.func.max(schuljahr_des_knotens()),
        )
        .where(
            ContextNode.content_type.in_((EINHEIT, STUNDE)),
            ContextNode.status.in_(LESBAR),
            sa.or_(
                ContextNode.write_scope_group_id.in_(mitglied_ids),
                sa.and_(
                    ContextNode.write_scope_group_id.in_(eigentum_ids),
                    ContextNode.owner_pseudonym == user.sub,
                ),
            ),
        )
        .group_by(ContextNode.write_scope_group_id, ContextNode.content_type)
    )
    for gid, typ, zahl, jahr in zeilen.all():
        eintrag = archiv[gid]
        if typ == EINHEIT:
            eintrag.einheiten = zahl
        else:
            eintrag.stunden = zahl
        if jahr and (eintrag.schuljahr is None or jahr > eintrag.schuljahr):
            eintrag.schuljahr = jahr

    # Eine Gruppe ohne Einheiten und Stunden hat im Archiv nichts zu zeigen.
    liste = [a for a in archiv.values() if a.einheiten or a.stunden]
    # Jüngstes Schuljahr zuerst, darin nach Namen („2025/26“ sortiert als Text richtig).
    liste.sort(key=lambda a: a.gruppe.anzeigename.casefold())
    liste.sort(key=lambda a: a.schuljahr or "", reverse=True)
    return liste


async def archiv_zugang(db: AsyncSession, group_id: int, user: JwtPayload) -> str | None:
    """`mitglied`, `eigentum` oder None (dann 404 — kein Hinweis, ob es die Gruppe gibt)."""
    zeile = await db.execute(
        sa.select(GroupMembership.group_id).where(
            GroupMembership.group_id == group_id, mitglied(user.sub, "teacher")
        )
    )
    if zeile.first() is not None:
        return MITGLIED
    if not eigenes_zaehlt(user.sub):
        return None
    zeile = await db.execute(
        _eigene_gruppen_ids(user.sub).where(ContextNode.write_scope_group_id == group_id)
    )
    return EIGENTUM if zeile.first() is not None else None


def _ordne(stunden: dict[UUID, ContextNode], folgt: dict[UUID, UUID]) -> list[UUID]:
    """Reihenfolge über `follows` (a folgt b), Rest nach Anlegedatum — wie `_build_lesson_nav`.

    Robust gegen Lücken: Fehlt eine Stunde in der Kette (fremd oder gelöscht), beginnt an der
    nächsten eine neue Kette. Zyklen enden am Besuchten.
    """
    nach = {}
    for a, b in folgt.items():
        if a in stunden and b in stunden:
            nach[b] = a
    vorgaenger = {a for a, b in folgt.items() if a in stunden and b in stunden}
    anfaenge = sorted(
        (sid for sid in stunden if sid not in vorgaenger),
        key=lambda sid: stunden[sid].created_at,
    )
    reihe: list[UUID] = []
    gesehen: set[UUID] = set()
    for anfang in anfaenge:
        aktuell = anfang
        while aktuell is not None and aktuell not in gesehen:
            reihe.append(aktuell)
            gesehen.add(aktuell)
            aktuell = nach.get(aktuell)
    rest = sorted((sid for sid in stunden if sid not in gesehen), key=lambda s: stunden[s].created_at)
    return reihe + rest


async def archiv_inhalt(
    db: AsyncSession,
    gruppe: Group,
    fach: Subject | None,
    zugang: str,
    user: JwtPayload,
    stati: tuple[str, ...] = LESBAR,
) -> ArchivInhalt:
    """Einheiten mit ihren Stunden in Reihenfolge, dazu „Stunden ohne Einheit“.

    Auch die Einheitenansicht des Planers (0.42.3) liest hierüber — dort mit
    `stati=("active",)`, also dem, was auch die Jahresübersicht zeigt.
    """
    nur_eigene = zugang == EIGENTUM
    bedingung = [
        ContextNode.write_scope_group_id == gruppe.id,
        ContextNode.status.in_(stati),
    ]
    stunden_abfrage = sa.select(ContextNode).where(ContextNode.content_type == STUNDE, *bedingung)
    if nur_eigene:
        stunden_abfrage = stunden_abfrage.where(ContextNode.owner_pseudonym == user.sub)
    stunden = {n.id: n for n in (await db.execute(stunden_abfrage)).scalars()}

    kanten = []
    if stunden:
        kanten = (
            await db.execute(
                sa.select(ContextEdge.from_node_id, ContextEdge.to_node_id, ContextEdge.relation).where(
                    ContextEdge.from_node_id.in_(list(stunden)),
                    ContextEdge.relation.in_(("part_of", "follows")),
                )
            )
        ).all()
    teil_von = {a: b for a, b, rel in kanten if rel == "part_of"}
    folgt = {a: b for a, b, rel in kanten if rel == "follows"}

    einheiten_abfrage = sa.select(ContextNode).where(ContextNode.content_type == EINHEIT, *bedingung)
    if nur_eigene:
        eigen = ContextNode.owner_pseudonym == user.sub
        mit_eigener_stunde = set(teil_von.values())
        einheiten_abfrage = einheiten_abfrage.where(
            sa.or_(eigen, ContextNode.id.in_(mit_eigener_stunde)) if mit_eigener_stunde else eigen
        )
    einheiten = {n.id: n for n in (await db.execute(einheiten_abfrage)).scalars()}

    termine: dict[UUID, tuple[date, bool, UUID]] = {}
    if stunden:
        for sid, datum, nachbereitet_at, slot_id in (
            await db.execute(
                sa.select(
                    LessonSlot.stunde_node_id, LessonSlot.date, LessonSlot.nachbereitet_at, LessonSlot.id
                ).where(LessonSlot.stunde_node_id.in_(list(stunden)))
            )
        ).all():
            termine[sid] = (datum, nachbereitet_at is not None, slot_id)

    def stunde(sid: UUID) -> ArchivStunde:
        n = stunden[sid]
        datum, nachbereitet, slot_id = termine.get(sid, (None, False, None))
        return ArchivStunde(
            id=n.id,
            titel=n.title,
            stundenziel=(n.metadata_ or {}).get("stundenziel"),
            datum=datum,
            nachbereitet=nachbereitet,
            archiviert=n.status == "archived",
            slot_id=slot_id,
        )

    je_einheit: dict[UUID, dict[UUID, ContextNode]] = {eid: {} for eid in einheiten}
    ohne: dict[UUID, ContextNode] = {}
    for sid, n in stunden.items():
        eid = teil_von.get(sid)
        if eid in je_einheit:
            je_einheit[eid][sid] = n
        else:
            ohne[sid] = n

    def erstes_datum(eid: UUID) -> date:
        daten = [termine[s][0] for s in je_einheit[eid] if s in termine]
        return min(daten) if daten else einheiten[eid].created_at.date()

    liste = [
        ArchivEinheit(
            id=e.id,
            titel=e.title,
            farbe=(e.metadata_ or {}).get("farbe", 0),
            schuljahr=(e.metadata_ or {}).get("schuljahr"),
            archiviert=e.status == "archived",
            stunden=[stunde(s) for s in _ordne(je_einheit[e.id], folgt)],
        )
        for e in sorted(einheiten.values(), key=lambda e: (erstes_datum(e.id), e.title))
    ]
    ohne_liste = sorted(
        (stunde(s) for s in ohne),
        key=lambda s: (s.datum or date.max, s.titel),
    )
    return ArchivInhalt(gruppe, fach, zugang, liste, ohne_liste)
