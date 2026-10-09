"""Eine Stunde im Chat finden und wählen (0.15, Päckchen A Schritt 3).

Die Stundenplanung greift ohne Gruppenbezug (Plan F9): „meine Stunde morgen in der 9d"
soll im freien Chat genügen. Die Werkzeuge `finde_stunde` und `waehle_stunde`
(`assistant_tools.py`) tragen das; hier steht, was sie tun.

⚠️ **Der Mitgliedschaftsfilter ist die Zugriffsregel** — wie bei `mein-tag`: Kandidaten
kommen nur aus Unterrichtsgruppen, in denen die Person **Lehrkraft** ist. Fällt er weg,
findet das Modell die Stunden der Kolleg:innen. Ein Wächtertest hält das fest.

**Das Datum rechnet der Server**, nicht das Modell (Muster `_ZEITRAEUME` im Chat-Router):
Es kennt das heutige Datum nicht zuverlässig, und eine Stunde vom falschen Donnerstag sieht
genauso richtig aus wie die gemeinte.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContextNode, Conversation, Group, GroupMembership, LessonSlot, Subject
from app.planning.mein_tag import MAX_VORLAUF_TAGE, stundenbezeichnung
from app.planning.permissions import ist_gruppenlehrkraft
from app.planning.service import entwurf_am_termin

WANN = ("heute", "morgen", "naechste", "diese_woche", "naechste_woche", "letzte_woche", "datum")
WOCHENTAGE = ("mo", "di", "mi", "do", "fr", "sa", "so")
MAX_TREFFER = 10


def lies_datum(text: str, heute: date) -> date | None:
    """„2026-10-15", „15.10.2026", „15.10.26" oder „15.10." — sonst ``None``.

    Ohne Jahr das zu ``heute`` nächstliegende: „3.1." im Dezember ist der kommende Januar,
    „28.12." im Januar der vergangene Dezember.
    """
    text = (text or "").strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    treffer = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})?", text)
    if treffer is None:
        return None
    tag, monat, jahr = int(treffer[1]), int(treffer[2]), treffer[3]
    if jahr:
        try:
            return date(int(jahr) + (2000 if len(jahr) == 2 else 0), monat, tag)
        except ValueError:
            return None
    kandidaten = []
    for j in (heute.year - 1, heute.year, heute.year + 1):
        try:
            kandidaten.append(date(j, monat, tag))
        except ValueError:
            continue
    return min(kandidaten, key=lambda d: abs((d - heute).days)) if kandidaten else None


def zeitraum(wann: str, heute: date, *, datum: date | None = None) -> tuple[date, date] | None:
    """``wann`` → (von, bis), beide einschließlich. Unbekannt oder ``datum`` fehlt → ``None``.

    ``morgen`` heißt der Kalendertag — anders als „Mein Tag", das den nächsten *Schultag*
    zeigt: Wer am Freitag „morgen" sagt, meint nicht Montag. Für „die nächste Stunde" gibt
    es ``naechste``.
    """
    montag = heute - timedelta(days=heute.weekday())
    if wann == "heute":
        return heute, heute
    if wann == "morgen":
        morgen = heute + timedelta(days=1)
        return morgen, morgen
    if wann == "naechste":
        return heute, heute + timedelta(days=MAX_VORLAUF_TAGE)
    if wann == "diese_woche":
        return montag, montag + timedelta(days=6)
    if wann == "naechste_woche":
        return montag + timedelta(days=7), montag + timedelta(days=13)
    if wann == "letzte_woche":
        return montag - timedelta(days=7), montag - timedelta(days=1)
    if wann == "datum" and datum is not None:
        return datum, datum
    return None


def flach(text: str | None) -> str:
    """Für Teiltreffer: klein, ohne Leerzeichen und Trennzeichen — „Ch-9 d" → „ch9d"."""
    return re.sub(r"[\s\-_./]", "", (text or "").lower())


def _wochentag(d: date) -> str:
    return WOCHENTAGE[d.weekday()].capitalize()


@dataclass
class Suche:
    wann: str
    datum: str | None = None
    wochentag: str | None = None
    gruppe: str | None = None
    fach: str | None = None
    thema: str | None = None

    def beschreibung(self, von: date, bis: date) -> str:
        teile = [f"{von.isoformat()} bis {bis.isoformat()}" if von != bis else von.isoformat()]
        if self.wann == "naechste":
            teile.insert(0, "je Gruppe der nächste Termin")
        for name, wert in (("Wochentag", self.wochentag), ("Gruppe", self.gruppe),
                           ("Fach", self.fach), ("Thema", self.thema)):
            if wert:
                teile.append(f"{name} „{wert}“")
        return ", ".join(teile)


async def finde_stunden(db: AsyncSession, pseudonym: str, suche: Suche, *, heute: date) -> dict:
    """Termine aus den eigenen Unterrichtsgruppen, die zur Suche passen — höchstens zehn."""
    datum = None
    if suche.wann == "datum":
        datum = lies_datum(suche.datum or "", heute)
        if datum is None:
            return {"error": f"„{suche.datum or ''}“ ist kein Datum. Erwartet: 15.10. oder 2026-10-15."}
    grenzen = zeitraum(suche.wann, heute, datum=datum)
    if grenzen is None:
        return {"error": f"Unbekanntes „wann“: {suche.wann}. Möglich: {', '.join(WANN)}."}
    von, bis = grenzen
    wochentag = (suche.wochentag or "").strip().lower()[:2] or None
    if wochentag is not None and wochentag not in WOCHENTAGE:
        return {"error": f"Unbekannter Wochentag „{suche.wochentag}“. Möglich: {', '.join(WOCHENTAGE)}."}

    # ⚠️ Die Zugriffsregel: nur Gruppen, in denen die Person Lehrkraft ist.
    eigene = sa.select(GroupMembership.group_id).where(
        GroupMembership.pseudonym == pseudonym,
        GroupMembership.role_in_group == "teacher",
    )
    zeilen = (
        await db.execute(
            sa.select(LessonSlot, Group, Subject)
            .join(Group, Group.id == LessonSlot.group_id)
            .outerjoin(Subject, Subject.id == Group.subject_id)
            .where(
                LessonSlot.group_id.in_(eigene),
                Group.type == "teaching_group",
                LessonSlot.date >= von,
                LessonSlot.date <= bis,
            )
            .order_by(LessonSlot.date, LessonSlot.start_period.asc().nullslast(), LessonSlot.group_id)
        )
    ).all()

    # Titel von Stunde und Einheit — für das Thema, in einer Abfrage.
    knoten_ids = {i for s, _, _ in zeilen for i in (s.stunde_node_id, s.ue_node_id) if i}
    titel: dict[UUID, str] = {}
    if knoten_ids:
        titel = dict((await db.execute(
            sa.select(ContextNode.id, ContextNode.title).where(ContextNode.id.in_(knoten_ids))
        )).all())

    gruppe, fach, thema = flach(suche.gruppe), flach(suche.fach), flach(suche.thema)
    passend = []
    gesehene_gruppen: set[int] = set()
    for slot, grp, subj in zeilen:
        if wochentag is not None and WOCHENTAGE[slot.date.weekday()] != wochentag:
            continue
        if gruppe and gruppe not in flach(grp.display_name) and gruppe not in flach(grp.name):
            continue
        if fach and not (subj and (fach in flach(subj.name) or fach in flach(subj.slug))):
            continue
        stundentitel = titel.get(slot.stunde_node_id) if slot.stunde_node_id else None
        if thema and not any(thema in flach(t) for t in (
            slot.thema, stundentitel, titel.get(slot.ue_node_id) if slot.ue_node_id else None,
        )):
            continue
        if suche.wann == "naechste":
            if slot.group_id in gesehene_gruppen:
                continue
            gesehene_gruppen.add(slot.group_id)
        passend.append({
            "slot_id": str(slot.id),
            "datum": slot.date.isoformat(),
            "wochentag": _wochentag(slot.date),
            "stunde": stundenbezeichnung(slot.start_period, slot.periods),
            "gruppe": grp.anzeigename,
            "fach": subj.name if subj else None,
            "thema": slot.thema or stundentitel,
            "kategorie": slot.kategorie,
            "hat_entwurf": slot.stunde_node_id is not None,
        })

    antwort = {
        "heute": f"{_wochentag(heute)} {heute.isoformat()}",
        "gesucht": suche.beschreibung(von, bis),
        "gesamt": len(passend),
        "treffer": passend[:MAX_TREFFER],
    }
    if len(passend) > MAX_TREFFER:
        antwort["hinweis"] = (
            f"{len(passend)} Termine passen, gezeigt sind die ersten {MAX_TREFFER}. "
            "Frage nach Gruppe, Fach oder Tag, statt zu raten."
        )
    return antwort


@dataclass
class Wahl:
    """Ergebnis von :func:`waehle`: entweder ``stunde`` oder ``antwort`` für das Modell."""

    stunde: ContextNode | None = None
    group_id: int | None = None
    neu: bool = False
    antwort: dict | None = None


async def waehle(
    db: AsyncSession, user, conversation_id: UUID | None, slot_id: UUID, *, anlegen: bool
) -> Wahl:
    """Macht den Termin zur Bezugsstunde der Konversation — und setzt deren Gruppe.

    Zugang wie beim Setzen aus der Entwurfsansicht (`stundenbezug.stunde_fuer_bezug`): nur
    als Lehrkraft der Gruppe. Fremd und unbekannt sind nicht zu unterscheiden.

    Einen Entwurf legt es nur mit ``anlegen`` an — dieselbe Funktion wie
    `POST /planning/slots/{id}/lesson` (`entwurf_am_termin`). Die Zustimmung der Lehrkraft
    einzuholen, ist Sache des Prompts.
    """
    slot = await db.get(LessonSlot, slot_id)
    gruppe = await db.get(Group, slot.group_id) if slot is not None else None
    if (
        gruppe is None
        or gruppe.type != "teaching_group"
        or not await ist_gruppenlehrkraft(gruppe.id, user, db)
    ):
        return Wahl(antwort={"error": "Termin nicht gefunden"})

    konversation = await db.get(Conversation, conversation_id) if conversation_id else None
    if konversation is None or konversation.pseudonym != user.sub:
        return Wahl(antwort={"error": "Keine Unterhaltung, an die sich die Stunde heften ließe"})

    stunde = None
    if slot.stunde_node_id:
        vorhanden = await db.get(ContextNode, slot.stunde_node_id)
        if vorhanden is not None and vorhanden.status == "active":
            stunde = vorhanden
    neu = False
    if stunde is None:
        if not anlegen:
            return Wahl(antwort={
                "slot_id": str(slot.id),
                "hat_entwurf": False,
                "hinweis": (
                    "Für diesen Termin gibt es noch keinen Stundenentwurf. Frage die Lehrkraft, "
                    "ob einer angelegt werden soll; wenn ja, rufe waehle_stunde mit "
                    "anlegen=true auf."
                ),
            })
        stunde, neu = await entwurf_am_termin(db, slot, user)

    konversation.group_id = gruppe.id
    konversation.subject_id = gruppe.subject_id
    konversation.stunde_node_id = stunde.id
    await db.commit()
    return Wahl(stunde=stunde, group_id=gruppe.id, neu=neu)
