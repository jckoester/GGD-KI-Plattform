"""Persönlicher Ausfall — welche Stunden er trifft und was er dabei überschreibt.

Die Regel steht hier als **reine Funktion**, ohne Datenbank: Was sie entscheidet, hängt
allein an den Slots, der Reichweite und dem, was schon dasteht. Dasselbe Muster wie
`plan_sync`/`apply_sync` und `plan_umhaengen`/`wende_umhaengen_an`.

⚠️ **Die Mechanik markiert und schlägt vor — sie handelt nicht** (Jan, 24.09.2026): „Je
nach Unterrichtsgruppe werden die Auswirkungen eines Ausfalls sehr unterschiedlich sein:
Inhalte können entfallen, mehrere geplante Stunden inhaltlich komprimiert werden oder der
ganze Plan verschoben werden. Das ist aktive Arbeit der Lehrkraft." Diese Datei setzt
deshalb nur die Kategorie und merkt sich den Rückweg; was daraus folgt, entscheidet die
Lehrkraft (AP5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Protocol
from uuid import UUID

#: Wer die Markierung gesetzt hat. Der Stundenplan-Abgleich darf die Kategorie nur
#: überschreiben, wo er selbst die Quelle ist — dieselbe Regel wie bei
#: `group_memberships.herkunft` (Paket 1).
HERKUENFTE = ("stundenplan", "eigen", "assistent")

#: Reichweite eines selbst eingetragenen Ausfalls.
#: `gruppe` = nur die bearbeitete Unterrichtsgruppe, `tag` = alle Gruppen der Lehrkraft.
REICHWEITEN = ("gruppe", "tag")

AUSFALL = "ausfall"


class SlotArtig(Protocol):
    """Was die Regel von einem Slot braucht — ORM-Objekt oder Attrappe."""

    id: UUID
    group_id: int
    date: date
    kategorie: str
    ausfall_herkunft: Optional[str]
    ausfall_vorher: Optional[str]


@dataclass(frozen=True)
class Markierung:
    """Ein Slot, der ausfallen soll — samt dem, was dabei überschrieben wird."""

    slot_id: UUID
    group_id: int
    vorher: str


@dataclass(frozen=True)
class Ruecknahme:
    """Ein Slot, der zurückgesetzt wird — auf genau diese Kategorie."""

    slot_id: UUID
    group_id: int
    zurueck_auf: str


def plane_ausfall(
    slots: Iterable[SlotArtig],
    *,
    datum: date,
    reichweite: str,
    group_id: int | None = None,
) -> tuple[Markierung, ...]:
    """Welche Stunden ein Ausfalleintrag trifft.

    `reichweite='tag'` nimmt **alle** übergebenen Gruppen an diesem Datum — Fortbildung
    und Krankheit gelten nicht je Fach. `reichweite='gruppe'` verlangt `group_id`.

    ⚠️ **Schon ausgefallene Stunden bleiben unangetastet**, gleich welcher Herkunft. Sie
    ein zweites Mal zu markieren überschriebe `ausfall_vorher` mit `'ausfall'` — und der
    Rückweg führte dann nirgendwohin.
    """
    if reichweite not in REICHWEITEN:
        raise ValueError(f"Unbekannte Reichweite: {reichweite!r}")
    if reichweite == "gruppe" and group_id is None:
        raise ValueError("Reichweite 'gruppe' verlangt eine group_id")

    return tuple(
        Markierung(slot_id=s.id, group_id=s.group_id, vorher=s.kategorie)
        for s in slots
        if s.date == datum
        and s.kategorie != AUSFALL
        and (reichweite == "tag" or s.group_id == group_id)
    )


def plane_ruecknahme(
    slots: Iterable[SlotArtig],
    *,
    datum: date,
    reichweite: str,
    group_id: int | None = None,
) -> tuple[Ruecknahme, ...]:
    """Welche Stunden ein Zurücknehmen wiederherstellt — und worauf.

    Zurückgenommen wird **nur Eigenes** (`ausfall_herkunft = 'eigen'`). Ein Ausfall aus
    dem Stundenplan gehört dem Abgleich; ihn hier zu entfernen hieße, eine Auskunft der
    Schule zu überschreiben, die beim nächsten Lauf ohnehin wiederkäme.

    ⚠️ **Einzeln gesetzte eigene Ausfälle gehen mit** (entschieden 24.09.2026, F4). Nach
    dem Schreiben ist nicht mehr unterscheidbar, ob ein Slot über „ganzer Tag" oder
    einzeln markiert wurde. Hinnehmbar — aber die Oberfläche muss es **vorher sagen**,
    statt es geschehen zu lassen.

    Ohne gemerkten Vorzustand geht es zurück auf `unterricht`: Das ist die Annahme, die
    `ausfall_vorher` gerade vermeiden soll, hier aber der einzige Ausweg — etwa bei
    Slots, die die Migration 0075 vorgefunden hat.
    """
    if reichweite not in REICHWEITEN:
        raise ValueError(f"Unbekannte Reichweite: {reichweite!r}")
    if reichweite == "gruppe" and group_id is None:
        raise ValueError("Reichweite 'gruppe' verlangt eine group_id")

    return tuple(
        Ruecknahme(
            slot_id=s.id,
            group_id=s.group_id,
            zurueck_auf=s.ausfall_vorher or "unterricht",
        )
        for s in slots
        if s.date == datum
        and s.kategorie == AUSFALL
        and s.ausfall_herkunft == "eigen"
        and (reichweite == "tag" or s.group_id == group_id)
    )




def setze_kategorie(slot, neu: str, *, herkunft: str) -> None:
    """Eine Kategorie setzen und die Ausfall-Angaben konsistent halten.

    ⚠️ **Die eine Stelle, an der die drei Felder zusammen bewegt werden.** `kategorie`,
    `ausfall_herkunft` und `ausfall_vorher` gehören zusammen; wer nur das erste setzt,
    hinterlässt entweder einen ungeschützten Ausfall (der nächste Stundenplan-Abgleich
    macht ihn lautlos rückgängig) oder eine zurückgebliebene Herkunft an einer Stunde,
    die längst wieder stattfindet.

    Es gibt keine Datenbank-Bedingung dafür — der Snapshot-Restore schreibt `kategorie`
    aus einem JSON, das die Spalten nicht kennt (siehe Alembic 0075). Diese Funktion ist
    der Ersatz: **ein** Ort statt einer Zusage, an die sich alle halten müssten.
    """
    if herkunft not in HERKUENFTE:
        raise ValueError(f"Unbekannte Herkunft: {herkunft!r}")
    if neu == AUSFALL:
        if slot.kategorie != AUSFALL:
            slot.ausfall_vorher = slot.kategorie
        slot.ausfall_herkunft = herkunft
    else:
        slot.ausfall_herkunft = None
        slot.ausfall_vorher = None
    slot.kategorie = neu

# ── Schreibend ───────────────────────────────────────────────────────────────


async def lade_slots_am_tag(
    db, pseudonym: str, datum: date, *, group_id: int | None = None
) -> list:
    """Die Slots dieses Tages, auf die die Lehrkraft Zugriff hat.

    ⚠️ **Die Mitgliedschaft ist die Zugriffsregel** — wie überall in der Planung. Ohne
    diesen Filter markierte „ganzer Tag" die Stunden fremder Kolleg:innen mit; sie fiele
    niemandem auf, der die andere Gruppe nicht kennt.
    """
    import sqlalchemy as sa

    from app.db.models import GroupMembership, LessonSlot

    eigene = sa.select(GroupMembership.group_id).where(
        GroupMembership.pseudonym == pseudonym,
        GroupMembership.role_in_group == "teacher",
    )
    stmt = sa.select(LessonSlot).where(
        LessonSlot.group_id.in_(eigene), LessonSlot.date == datum
    )
    if group_id is not None:
        stmt = stmt.where(LessonSlot.group_id == group_id)
    return list((await db.execute(stmt)).scalars().all())


async def wende_ausfall_an(
    db,
    slots,
    markierungen: tuple[Markierung, ...],
    *,
    herkunft: str,
    notiz: str | None = None,
) -> int:
    """Setzt die geplanten Markierungen. Gibt zurück, wie viele Stunden betroffen sind."""
    from datetime import datetime, timezone

    from app.calendar.sync import mit_eigenem_text

    if herkunft not in HERKUENFTE:
        raise ValueError(f"Unbekannte Herkunft: {herkunft!r}")

    nach_id = {s.id: s for s in slots}
    jetzt = datetime.now(timezone.utc)
    for m in markierungen:
        slot = nach_id[m.slot_id]
        slot.kategorie = AUSFALL
        slot.ausfall_herkunft = herkunft
        slot.ausfall_vorher = m.vorher
        if notiz:
            # ⚠️ Über `mit_eigenem_text`, nicht durch Zuweisung: Eine vorhandene
            # `[Stundenplan]`-Zeile gehört dem Abgleich und muss stehen bleiben.
            slot.note = mit_eigenem_text(slot.note, notiz)
        slot.updated_at = jetzt
    return len(markierungen)


async def nimm_ausfall_zurueck(db, slots, ruecknahmen: tuple[Ruecknahme, ...]) -> int:
    """Setzt die Kategorien zurück und räumt die Herkunftsangaben weg."""
    from datetime import datetime, timezone

    nach_id = {s.id: s for s in slots}
    jetzt = datetime.now(timezone.utc)
    for r in ruecknahmen:
        slot = nach_id[r.slot_id]
        slot.kategorie = r.zurueck_auf
        slot.ausfall_herkunft = None
        slot.ausfall_vorher = None
        slot.updated_at = jetzt
    return len(ruecknahmen)
