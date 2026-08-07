"""Aus abgerufenen Wochen Wochenmuster ableiten (UP-8, Schritt 6).

Reine Funktionen — kein Netz, keine Datenbank. Was hier herauskommt, ist ein **Vorschlag**:
Die Lehrkraft bestätigt je Gruppe (Schritt 7 verknüpft ihn mit den Unterrichtsgruppen der
Plattform).

Drei Entscheidungen prägen das Ergebnis:

1. **Welche Stunden zählen.** Eine ausgefallene oder vertretene Stunde gehört zum Muster —
   sie stand im Plan. Eine **verlegte** dagegen nicht: Der `SHIFT`-Termin ist ein
   einmaliges Vorkommnis an ungewöhnlicher Position und würde als Muster ein Phantom
   erzeugen. Übernommene Aufsicht (`covering_for`) ist fremder Unterricht.
2. **Rhythmus.** Wöchentlich oder 14-tägig, entschieden über die Anzahl der Wochen, in
   denen eine Position vorkam.
3. **Doppelstunden.** Zwei aufeinanderfolgende Stunden verschmelzen nur, wenn sie im
   Zeitraster **lückenlos** aneinandergrenzen.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.calendar.base import Lesson, LessonState

# Zustände, die belegen, dass an dieser Position regulär Unterricht steht.
#
# `CANCELLED` und `SUBSTITUTION` gehören dazu: Die Stunde ist ausgefallen bzw. wurde
# beaufsichtigt, aber sie **stand im Plan** — genau das soll das Muster abbilden.
# `SHIFTED` gehört NICHT dazu: Das ist das Ziel einer Verlegung, ein einmaliger Termin an
# einer Position, an der sonst nichts liegt.
MUSTER_ZUSTAENDE = frozenset(
    {
        LessonState.REGULAR,
        LessonState.EXAM,
        LessonState.CANCELLED,
        LessonState.SUBSTITUTION,
    }
)

WOECHENTLICH = "woechentlich"
A_WOCHE = "a_woche"
B_WOCHE = "b_woche"


@dataclass(frozen=True)
class GroupKey:
    """Woran eine Lerngruppe erkannt wird.

    `student_group` ist der verlässliche Schlüssel (am GGD `ET_5_BU` = Fach_Jahrgang_
    Kürzel). Fehlt er — in der Aufzeichnung bei einem Teil der Stunden —, tritt die
    Kombination aus Fach und Klassen an seine Stelle. Beides zu mischen wäre schlecht:
    Dieselbe Gruppe erschiene doppelt.
    """

    student_group: str | None
    subject: str | None
    class_names: tuple[str, ...]

    @property
    def identifizierbar(self) -> bool:
        """Ob sich daraus überhaupt eine Lerngruppe benennen lässt.

        Nein heißt: keine Gruppenkennung, kein Fach, keine Klasse. In den echten Daten
        trifft das die **Pausenaufsicht** — die trägt nur einen Raum (`HOF-S`, `MENSA`).
        Steht sie ausnahmsweise als Vertretung im Plan, rutscht sie durch den
        Zustandsfilter und erzeugte sonst ein Muster ohne Gruppe.
        """
        return bool(self.student_group or self.subject or self.class_names)

    @property
    def label(self) -> str:
        if self.student_group:
            return self.student_group
        teile = [self.subject or "?"]
        if self.class_names:
            teile.append("/".join(self.class_names))
        return " ".join(teile)


@dataclass
class PatternProposal:
    """Ein vorgeschlagener Eintrag in `group_week_patterns`."""

    key: GroupKey
    weekday: int            # 0 = Montag
    start_period: int
    periods: int
    rhythmus: str
    gesehen: int            # in wie vielen der abgerufenen Wochen
    wochen: int             # wie viele Wochen abgerufen wurden

    @property
    def sicher(self) -> bool:
        """Ob die Beobachtung den Rhythmus trägt.

        Wöchentlich braucht jede Woche, 14-tägig die Hälfte. Alles dazwischen ist ein
        Muster mit Lücken — meist wegen Feiertagen, manchmal wegen eines Fehlers. Es wird
        vorgeschlagen, aber gekennzeichnet.
        """
        if self.rhythmus == WOECHENTLICH:
            return self.gesehen == self.wochen
        return self.gesehen * 2 >= self.wochen


@dataclass
class PatternResult:
    proposals: list[PatternProposal] = field(default_factory=list)
    wochen: list[date] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)


def contiguous_periods(timegrid: list[tuple[int, int]]) -> set[int]:
    """Stundennummern, nach denen die nächste **lückenlos** anschließt (1-basiert).

    Das ist die Doppelstunden-Regel — ohne geratenen Schwellwert. Am GGD ist der
    Unterschied eindeutig: Doppelstunden haben Lücke 0, jede Pause misst 5 bis 30 Minuten.
    Fehlt das Raster, gibt es keine Doppelstunden; das entspricht der Vorgabe des Plans,
    im Zweifel zwei Einzelstunden vorzuschlagen — die lassen sich leichter zusammenfassen
    als trennen.
    """
    return {
        nummer
        for nummer, (_, ende) in enumerate(timegrid[:-1], start=1)
        if timegrid[nummer][0] == ende
    }


def week_index(tag: date, anker: date) -> int:
    """Nummer der Kalenderwoche relativ zum Anker (0 = Woche des Ankers)."""
    montag = tag - timedelta(days=tag.weekday())
    anker_montag = anker - timedelta(days=anker.weekday())
    return (montag - anker_montag).days // 7


def _gruppe(lesson: Lesson) -> GroupKey:
    return GroupKey(
        student_group=lesson.student_group,
        subject=lesson.subject,
        class_names=lesson.class_names,
    )


def derive_patterns(
    lessons: list[Lesson],
    *,
    wochen: list[date],
    timegrid: list[tuple[int, int]] | None = None,
    anker: date | None = None,
    kein_unterricht: frozenset[str] | None = None,
) -> PatternResult:
    """Wochenmuster aus den Stunden mehrerer Wochen ableiten.

    `wochen` sind die abgerufenen Kalenderwochen (beliebiger Tag darin) — sie bestimmen
    den Nenner: Ohne sie ließe sich „kam in 2 von 4 Wochen vor" nicht von „kam zweimal
    vor" unterscheiden, und jede Rhythmus-Aussage wäre geraten.

    `kein_unterricht` sind Fachkürzel, hinter denen kein Unterricht steht (Präsenzstunde,
    Personalrats- oder Schulleitungssitzung). Sie erzeugen kein Muster — der Stundenplan
    führt sie wie Unterricht, die Jahresplanung kennt sie nicht.

    `anker` legt fest, welche Woche A ist (Vorgabe: die früheste abgerufene). Der Plan
    sieht dafür ein Datum in `school_year.yaml` vor; solange es fehlt, ist die Zuordnung
    eine **Konvention** — welche der beiden Wochen A heißt, muss die Lehrkraft prüfen.
    """
    ergebnis = PatternResult(wochen=sorted(wochen))
    if not wochen:
        ergebnis.hinweise.append("Keine Wochen abgerufen — kein Muster ableitbar.")
        return ergebnis

    anker = anker or min(wochen)
    wochen_index = {week_index(w, anker) for w in wochen}
    anzahl_wochen = len(wochen_index)
    zusammenhaengend = contiguous_periods(timegrid or [])

    # (Gruppe, Wochentag, Stunde) → in welchen Wochen gesehen
    ausgeschlossen = kein_unterricht or frozenset()
    beobachtung: dict[tuple[GroupKey, int, int], set[int]] = defaultdict(set)
    ohne_stunde = 0
    ohne_gruppe = 0
    dienstliches: set[str] = set()

    for lesson in lessons:
        if lesson.covering_for or lesson.state not in MUSTER_ZUSTAENDE:
            continue
        if lesson.subject and lesson.subject.strip().upper() in ausgeschlossen:
            dienstliches.add(lesson.subject.strip().upper())
            continue
        if not _gruppe(lesson).identifizierbar:
            ohne_gruppe += 1
            continue
        if lesson.start_period is None:
            ohne_stunde += 1
            continue
        index = week_index(lesson.date, anker)
        if index not in wochen_index:
            continue
        for versatz in range(max(1, lesson.periods)):
            beobachtung[
                (_gruppe(lesson), lesson.date.weekday(), lesson.start_period + versatz)
            ].add(index)

    if ohne_stunde:
        ergebnis.hinweise.append(
            f"{ohne_stunde} Stunden ohne Stundennummer übersprungen — Zeitraster fehlt."
        )
    if ohne_gruppe:
        ergebnis.hinweise.append(
            f"{ohne_gruppe} Termine ohne Fach und Klasse übersprungen "
            f"(typisch: Pausenaufsicht)."
        )
    if dienstliches:
        # Bewusst als schlichte Feststellung, nicht als Mangel: Hier ist nichts zu tun.
        ergebnis.hinweise.append(
            "Nicht als Unterricht gewertet: " + ", ".join(sorted(dienstliches)) + "."
        )

    # Erst je Einzelstunde den Rhythmus bestimmen, dann benachbarte verschmelzen. Die
    # umgekehrte Reihenfolge verschmölze Stunden mit verschiedenen Rhythmen.
    einzeln: dict[tuple[GroupKey, int], dict[int, tuple[str, int]]] = defaultdict(dict)
    for (key, weekday, stunde), indizes in beobachtung.items():
        einzeln[(key, weekday)][stunde] = (
            _rhythmus(indizes, wochen_index, anzahl_wochen),
            len(indizes),
        )

    for (key, weekday), stunden in sorted(
        einzeln.items(), key=lambda eintrag: (eintrag[0][0].label, eintrag[0][1])
    ):
        for start, laenge, rhythmus, gesehen in _bloecke(stunden, zusammenhaengend):
            ergebnis.proposals.append(
                PatternProposal(
                    key=key,
                    weekday=weekday,
                    start_period=start,
                    periods=laenge,
                    rhythmus=rhythmus,
                    gesehen=gesehen,
                    wochen=anzahl_wochen,
                )
            )

    ergebnis.proposals.sort(
        key=lambda p: (p.key.label, p.weekday, p.start_period)
    )
    if anzahl_wochen < 2:
        ergebnis.hinweise.append(
            "Nur eine Woche abgerufen — 14-tägige Termine sind so nicht von wöchentlichen "
            "zu unterscheiden. Alles gilt als wöchentlich."
        )
    return ergebnis


def _rhythmus(indizes: set[int], alle: set[int], anzahl: int) -> str:
    """Wöchentlich oder 14-tägig — und wenn 14-tägig, welche Woche.

    Bei nur einer abgerufenen Woche ist die Frage nicht entscheidbar; dann gilt
    wöchentlich. Eine 14-tägige Vermutung aus einer einzigen Beobachtung wäre geraten.
    """
    if anzahl < 2 or len(indizes) == anzahl:
        return WOECHENTLICH
    gerade = {i for i in alle if i % 2 == 0}
    ungerade = alle - gerade
    if indizes == gerade and gerade:
        return A_WOCHE
    if indizes == ungerade and ungerade:
        return B_WOCHE
    return WOECHENTLICH


def _bloecke(
    stunden: dict[int, tuple[str, int]], zusammenhaengend: set[int]
) -> list[tuple[int, int, str, int]]:
    """Benachbarte Stunden zu Blöcken verschmelzen.

    Verschmolzen wird nur, wenn die Stunden im Zeitraster lückenlos aneinandergrenzen
    **und** denselben Rhythmus haben. Ergebnis: (Beginn, Länge, Rhythmus, gesehen).
    """
    bloecke: list[tuple[int, int, str, int]] = []
    offen: list[int] = []
    for stunde in sorted(stunden):
        if offen:
            vorher = offen[-1]
            passt = (
                stunde == vorher + 1
                and vorher in zusammenhaengend
                and stunden[stunde][0] == stunden[vorher][0]
            )
            if not passt:
                bloecke.append(_block(offen, stunden))
                offen = []
        offen.append(stunde)
    if offen:
        bloecke.append(_block(offen, stunden))
    return bloecke


def _block(stunden_liste: list[int], stunden: dict[int, tuple[str, int]]):
    start = stunden_liste[0]
    rhythmus, _ = stunden[start]
    # Die vorsichtigere Zahl: Ein Block gilt nur so oft als gesehen, wie seine seltenste
    # Stunde vorkam. Sonst sähe ein Block sicherer aus als sein schwächstes Glied.
    gesehen = min(stunden[s][1] for s in stunden_liste)
    return (start, len(stunden_liste), rhythmus, gesehen)
