"""Entfall und Vertretung in die Jahresplanung übernehmen (UP-8, Schritt 8).

Der Abgleich ist **zweistufig**: `plan_sync` rechnet aus, was zu tun wäre — ohne
Datenbank, ohne Seiteneffekt; `apply_sync` führt es aus. Das erlaubt eine Vorschau vor dem
Schreiben und macht die Regeln prüfbar, ohne eine Datenbank aufzusetzen.

**Der Sync ändert Kategorien, keine Inhalte.** Thema, verknüpfte Unterrichtseinheit und
Stunde bleiben unangetastet — was aus einer ausgefallenen Stunde wird, entscheidet die
Lehrkraft im Verschiebe-Dialog aus UP-6. Drei Grenzen sichern das ab:

1. **`pinned` und `source='manual'` werden nie geändert**, nur gemeldet.
2. **Die Notiz wird nur ersetzt, wenn sie vom Import stammt** — erkennbar am Marker.
   Selbstgeschriebene Notizen bleiben, auch wenn sie im Weg stehen.
3. **Ohne passenden Slot wird nichts angelegt.** Eine Stunde, für die die Planung keinen
   Slot kennt, ist eine Abweichung — sie wird gemeldet, nicht stillschweigend behoben.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from app.calendar.base import SLOT_CATEGORY, Lesson, LessonState

logger = logging.getLogger(__name__)

# Präfix der vom Import geschriebenen Notizen. Nur was damit beginnt, wird überschrieben —
# so bleibt eine selbstgeschriebene Notiz erhalten und der Import trotzdem idempotent.
NOTIZ_MARKER = "[Stundenplan]"

# Ab wie vielen ausgefallenen Stunden an einem Tag zusammengefasst gemeldet wird. Zwei
# Ausfälle sind zwei Ereignisse; ab drei ist es erkennbar ein Tag, an dem etwas anderes
# stattfand (Wandertag, Projekttag) — und sechs Einzelmeldungen wären dann nur Lärm.
_TAGESMELDUNG_AB = 3


@dataclass(frozen=True)
class SlotChange:
    """Eine Änderung an genau einem Slot."""

    slot_id: object
    group_id: int
    datum: date
    start_period: int
    von_kategorie: str
    nach_kategorie: str
    anpassung_noetig: bool
    notiz: str | None
    external_uid: str | None

    @property
    def wirkt(self) -> bool:
        """Ob sich überhaupt etwas ändert — sonst ist der Schreibvorgang überflüssig."""
        return self.von_kategorie != self.nach_kategorie or self.notiz is not None


@dataclass(frozen=True)
class SyncConflict:
    """Etwas, das der Sync **nicht** angefasst hat, und warum."""

    datum: date
    start_period: int | None
    grund: str            # 'pinned' | 'manual' | 'kein_slot' | 'fremde_notiz'
    beschreibung: str


@dataclass
class SyncPlan:
    changes: list[SlotChange] = field(default_factory=list)
    conflicts: list[SyncConflict] = field(default_factory=list)
    meldungen: list[str] = field(default_factory=list)

    @property
    def wirksame_changes(self) -> list[SlotChange]:
        return [c for c in self.changes if c.wirkt]


@dataclass(frozen=True)
class SlotRef:
    """Der Ausschnitt eines `lesson_slots`-Eintrags, den der Abgleich braucht."""

    id: object
    group_id: int
    datum: date
    start_period: int
    kategorie: str
    pinned: bool
    source: str
    note: str | None


def _notiz_fuer(lesson: Lesson) -> str | None:
    """Die Notiz, die der Import setzen würde — oder None, wenn keine nötig ist."""
    if lesson.covered_by:
        return f"{NOTIZ_MARKER} Vertreten durch {lesson.covered_by}"
    return None


def _notiz_darf_geschrieben_werden(vorhanden: str | None) -> bool:
    """Nur leere oder vom Import stammende Notizen werden ersetzt.

    Eine selbstgeschriebene Notiz zu überschreiben wäre Datenverlust — und zwar einer, den
    niemand bemerkt, weil die neue Notiz plausibel aussieht.
    """
    return not (vorhanden or "").strip() or (vorhanden or "").lstrip().startswith(
        NOTIZ_MARKER
    )


def plan_sync(
    lessons: list[tuple[int, Lesson]],
    slots: list[SlotRef],
    *,
    zeitraum: tuple[date, date] | None = None,
) -> SyncPlan:
    """Was der Abgleich ändern würde. Keine Datenbank, kein Seiteneffekt.

    `lessons` sind Paare aus `groups.id` und Stunde — die Zuordnung trifft Schritt 7.
    `zeitraum` begrenzt auf die tatsächlich abgerufenen Tage: Ein Slot außerhalb wurde
    nicht geprüft und darf deshalb auch nicht geändert werden.
    """
    plan = SyncPlan()
    nach_position = {(s.group_id, s.datum, s.start_period): s for s in slots}
    gesehen: set[tuple[int, date, int]] = set()

    for group_id, lesson in lessons:
        if not lesson.creates_slot or lesson.start_period is None:
            continue
        if zeitraum and not (zeitraum[0] <= lesson.date <= zeitraum[1]):
            continue

        ziel = SLOT_CATEGORY.get(lesson.state)
        if ziel is None:
            continue

        for versatz in range(max(1, lesson.periods)):
            position = (group_id, lesson.date, lesson.start_period + versatz)
            if position in gesehen:
                continue
            gesehen.add(position)
            slot = nach_position.get(position)

            if slot is None:
                # Kein Slot an dieser Stelle: Die Planung kennt die Stunde nicht. Das ist
                # eine Abweichung, keine Aufgabe — angelegt wird hier nichts (Schritt 9
                # behandelt den häufigsten Fall, die Verlegung).
                plan.conflicts.append(
                    SyncConflict(
                        datum=lesson.date,
                        start_period=lesson.start_period + versatz,
                        grund="kein_slot",
                        beschreibung=(
                            f"Stundenplan kennt Unterricht, die Jahresplanung hat dort "
                            f"keinen Slot ({lesson.state.value})."
                        ),
                    )
                )
                continue

            if slot.pinned or slot.source == "manual":
                grund = "pinned" if slot.pinned else "manual"
                warum = "festgehalten" if slot.pinned else "von Hand gesetzt"
                plan.conflicts.append(
                    SyncConflict(
                        datum=slot.datum,
                        start_period=slot.start_period,
                        grund=grund,
                        beschreibung=(
                            f"Slot ist {warum} — Stundenplan meldet "
                            f"{lesson.state.value}, geändert wurde nichts."
                        ),
                    )
                )
                continue

            notiz = _notiz_fuer(lesson)
            if notiz is not None and not _notiz_darf_geschrieben_werden(slot.note):
                plan.conflicts.append(
                    SyncConflict(
                        datum=slot.datum,
                        start_period=slot.start_period,
                        grund="fremde_notiz",
                        beschreibung=(
                            "Eigene Notiz vorhanden — der Vertretungshinweis wurde nicht "
                            "geschrieben."
                        ),
                    )
                )
                notiz = None

            plan.changes.append(
                SlotChange(
                    slot_id=slot.id,
                    group_id=group_id,
                    datum=slot.datum,
                    start_period=slot.start_period,
                    von_kategorie=slot.kategorie,
                    nach_kategorie=ziel,
                    # Der Kern der Begriffsklärung (§2.1): Ausfall UND Vertretung lassen
                    # das Stundenziel offen — beides fordert Umplanung an.
                    anpassung_noetig=not lesson.delivers_planned_content,
                    notiz=notiz,
                    external_uid=lesson.external_uid,
                )
            )

    plan.meldungen = _meldungen(plan.wirksame_changes)
    return plan


def _meldungen(changes: list[SlotChange]) -> list[str]:
    """Menschenlesbare Zusammenfassung — Tage mit Vollausfall gebündelt.

    Ein Wandertag erzeugt sechs Ausfälle. Sechs Meldungen dazu sind kein Bericht, sondern
    eine Wand; die eine Aussage, die zählt, ist „an diesem Tag fand kein Unterricht statt".
    """
    ausfall_je_tag: dict[date, list[SlotChange]] = defaultdict(list)
    einzeln: list[SlotChange] = []
    for change in changes:
        if change.nach_kategorie == "ausfall":
            ausfall_je_tag[change.datum].append(change)
        else:
            einzeln.append(change)

    meldungen: list[str] = []
    for tag, gruppe in sorted(ausfall_je_tag.items()):
        if len(gruppe) >= _TAGESMELDUNG_AB:
            meldungen.append(
                f"{tag}: {len(gruppe)} Stunden fallen aus — vermutlich ein "
                f"unterrichtsfreier Tag."
            )
        else:
            meldungen.extend(
                f"{c.datum}, {c.start_period}. Stunde: Ausfall." for c in gruppe
            )
    for change in sorted(einzeln, key=lambda c: (c.datum, c.start_period)):
        beschreibung = {
            "vertretung": "wird vertreten (Aufsicht, kein Unterricht)",
            "unterricht": "findet statt",
            "pruefung": "Prüfung",
        }.get(change.nach_kategorie, change.nach_kategorie)
        meldungen.append(
            f"{change.datum}, {change.start_period}. Stunde: {beschreibung}."
        )
    return meldungen


async def apply_sync(db, plan: SyncPlan) -> int:
    """Den Plan ausführen. Gibt die Zahl geänderter Slots zurück.

    Geschrieben wird nur, was sich tatsächlich ändert — ein Sync ohne Neuigkeiten soll die
    `updated_at`-Zeitstempel nicht durchrütteln und keine Änderungshistorie erfinden.
    """
    from sqlalchemy import text

    geaendert = 0
    for change in plan.wirksame_changes:
        felder = [
            "kategorie = :kategorie",
            "anpassung_noetig = :anpassung",
            "source = 'import'",
            "external_uid = :uid",
            "updated_at = now()",
        ]
        params = {
            "id": change.slot_id,
            "kategorie": change.nach_kategorie,
            "anpassung": change.anpassung_noetig,
            "uid": change.external_uid,
        }
        if change.notiz is not None:
            felder.append("note = :notiz")
            params["notiz"] = change.notiz
        await db.execute(
            text(f"UPDATE lesson_slots SET {', '.join(felder)} WHERE id = :id"), params
        )
        geaendert += 1
    if geaendert:
        await db.commit()
    return geaendert
