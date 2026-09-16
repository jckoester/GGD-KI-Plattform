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
   denen eine Position vorkam — gemessen an den Wochen, in denen die Lehrkraft überhaupt
   Unterricht hatte. Eine Woche ohne eine einzige Stunde ist kein Beleg gegen einen
   wöchentlichen Rhythmus, sondern eine Woche ohne Daten.
3. **Doppelstunden.** Zwei aufeinanderfolgende Stunden verschmelzen nur, wenn sie im
   Zeitraster **lückenlos** aneinandergrenzen.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.calendar.base import Lesson, LessonState

# Die Rhythmus-Werte stehen dort, wo auch die Regel steht, die sie in konkrete Wochen
# übersetzt (`ab_phasen`). Zwei Umsetzungen derselben Regel drifteten irgendwann
# auseinander — und zwar lautlos: Erst Monate später fiele auf, dass die Stunden eine
# Woche verschoben liegen.
from app.planning.calendar import A_WOCHE, B_WOCHE, WOECHENTLICH

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
    phasen: dict[date, int] | None = None,
    kein_unterricht: frozenset[str] | None = None,
) -> PatternResult:
    """Wochenmuster aus den Stunden mehrerer Wochen ableiten.

    `wochen` sind die abgerufenen Kalenderwochen (beliebiger Tag darin) — sie bestimmen
    den Nenner: Ohne sie ließe sich „kam in 2 von 4 Wochen vor" nicht von „kam zweimal
    vor" unterscheiden, und jede Rhythmus-Aussage wäre geraten.

    Aus dem Nenner fallen Wochen, in denen die Lehrkraft **gar keine** Stunde hatte —
    Praktikums-, Projekt- oder bewegliche Ferienwoche. Sie belegen nichts; sie mitzuzählen
    machte aus jedem wöchentlichen Termin einen 14-tägigen, und weil 14-tägig schon bei
    der Hälfte als `sicher` gilt, wäre das Ergebnis zuversichtlich falsch. `ergebnis.wochen`
    nennt deshalb die Wochen, die tatsächlich gezählt haben, nicht die abgerufenen.

    `kein_unterricht` sind Fachkürzel, hinter denen kein Unterricht steht (Präsenzstunde,
    Personalrats- oder Schulleitungssitzung). Sie erzeugen kein Muster — der Stundenplan
    führt sie wie Unterricht, die Jahresplanung kennt sie nicht.

    `anker` ist der Nullpunkt der Wochen**zählung** — er unterscheidet die abgerufenen
    Wochen voneinander, mehr nicht (Vorgabe: die früheste abgerufene).

    `phasen` entscheidet, welche davon A- und welche B-Wochen sind: ein Mapping
    Montag → 0/1 aus `ab_phasen()`. Ohne das Mapping bliebe nur die Parität zum Anker —
    und die wandert mit dem Abrufzeitpunkt: Dieselbe 14-tägige Stunde hieß in einem
    Fenster ab dem 08.06. `a_woche` und in einem ab dem 15.06. `b_woche`, beide Male
    „sicher". Der Router reicht die Phasen des Schuljahres durch; ohne sie bleibt es beim
    alten Verhalten, damit die Funktion für sich benutzbar bleibt.
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
    mit_unterricht: set[int] = set()
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
        mit_unterricht.add(index)
        for versatz in range(max(1, lesson.periods)):
            beobachtung[
                (_gruppe(lesson), lesson.date.weekday(), lesson.start_period + versatz)
            ].add(index)

    # Leere Wochen aus dem Nenner nehmen — aber nur, wenn überhaupt etwas übrig bleibt.
    # Ist jede Woche leer, gibt es ohnehin keinen Vorschlag; dann bliebe nur eine
    # irreführend leere Wochenliste.
    leere = len(wochen_index) - len(mit_unterricht)
    if leere and mit_unterricht:
        ergebnis.hinweise.append(
            f"{leere} von {len(wochen_index)} Wochen enthielten keine einzige Stunde und "
            "zählen nicht mit (Praktikums-, Projekt- oder bewegliche Ferienwoche). "
            "Ein leer gebliebener Abruf sähe allerdings genauso aus."
        )
        wochen_index = mit_unterricht
        anzahl_wochen = len(wochen_index)
        ergebnis.wochen = [
            w for w in ergebnis.wochen if week_index(w, anker) in wochen_index
        ]

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

    phase_je_woche = {i: _phase(i, anker, phasen) for i in wochen_index}

    # Erst je Einzelstunde den Rhythmus bestimmen, dann benachbarte verschmelzen. Die
    # umgekehrte Reihenfolge verschmölze Stunden mit verschiedenen Rhythmen.
    # Die **Wochenmenge** wird mitgeführt, nicht nur ihre Größe: `_bloecke` verschmilzt
    # nur Stunden, die tatsächlich gemeinsam auftraten (siehe dort).
    einzeln: dict[tuple[GroupKey, int], dict[int, tuple[str, frozenset[int]]]] = (
        defaultdict(dict)
    )
    for (key, weekday, stunde), indizes in beobachtung.items():
        einzeln[(key, weekday)][stunde] = (
            _rhythmus(indizes, wochen_index, anzahl_wochen, phase_je_woche),
            frozenset(indizes),
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
            "Nur eine Woche mit Unterricht — 14-tägige Termine sind so nicht von wöchentlichen "
            "zu unterscheiden. Alles gilt als wöchentlich."
        )
    return ergebnis


def _phase(index: int, anker: date, phasen: dict[date, int] | None) -> int:
    """Ob die Woche mit dieser Nummer eine A- (0) oder eine B-Woche (1) ist.

    Fehlt das Mapping, bleibt nur die Parität zum Anker. Eine Woche, die das Mapping nicht
    kennt, läge außerhalb des Schuljahres — über den Endpunkt unerreichbar, denn der holt
    nur Unterrichtswochen.
    """
    if phasen is None:
        return index % 2
    montag = anker - timedelta(days=anker.weekday()) + timedelta(weeks=index)
    return phasen.get(montag, index % 2)


def _rhythmus(
    indizes: set[int], alle: set[int], anzahl: int, phase: dict[int, int]
) -> str:
    """Wöchentlich oder 14-tägig — und wenn 14-tägig, welche Woche.

    Bei nur einer abgerufenen Woche ist die Frage nicht entscheidbar; dann gilt
    wöchentlich. Eine 14-tägige Vermutung aus einer einzigen Beobachtung wäre geraten.

    Entschieden wird über **Teilmenge**, nicht über Gleichheit: Die beobachteten Wochen
    müssen in *eine* der beiden Paritätsklassen passen, sie müssen sie nicht ausfüllen.
    Bis zum 16.09.2026 war Gleichheit verlangt — fiel eine Stunde in der ersten A-Woche
    aus, war {3} weder gleich {1,3} noch gleich {2,4}, und die Funktion fiel auf ihren
    Vorgabewert `woechentlich` durch. Aus dem **schwächsten** Beleg wurde so die
    **stärkste** Behauptung:

    | Annahme      | erwartet | gesehen | fehlt |
    | ------------ | -------: | ------: | ----: |
    | A-Woche      |        2 |       1 |     1 |
    | wöchentlich  |        4 |       1 |     3 |

    Gewählt wird jetzt die Annahme, die weniger Fehlstellen braucht.

    **Die Kehrseite, bewusst in Kauf genommen:** Eine *wöchentliche* Stunde, die dreimal
    von vier ausfällt, heißt danach „A-Woche" statt „wöchentlich". Das ist derselbe Tausch
    zugunsten der besseren Erklärung — und beide Fälle sind über `sicher` als prüfbedürftig
    gekennzeichnet (1 von 4 erfüllt auch die 14-tägige Schwelle nicht).

    Verteilen sich die Beobachtungen über **beide** Paritäten, bleibt es wöchentlich: Dann
    erklärt keine 14-tägige Annahme die Daten.
    """
    if anzahl < 2 or len(indizes) == anzahl:
        return WOECHENTLICH
    a_wochen = {i for i in alle if phase[i] == 0}
    b_wochen = alle - a_wochen
    # `indizes` ist nie leer — ein Eintrag entsteht erst mit der ersten Beobachtung.
    if indizes <= a_wochen and a_wochen:
        return A_WOCHE
    if indizes <= b_wochen and b_wochen:
        return B_WOCHE
    return WOECHENTLICH


def _bloecke(
    stunden: dict[int, tuple[str, frozenset[int]]], zusammenhaengend: set[int]
) -> list[tuple[int, int, str, int]]:
    """Benachbarte Stunden zu Blöcken verschmelzen.

    Drei Bedingungen, alle notwendig: Die Stunden grenzen im Zeitraster lückenlos
    aneinander, haben denselben Rhythmus **und traten in denselben Wochen auf**.

    Die dritte kam aus der Abnahme an echten Daten (Schritt 13). Ohne sie zog eine
    einmalige Klassenarbeit, die in die Folgestunde hineinreichte, die davorliegende
    **wöchentliche** Stunde in einen Block — Ergebnis war „Doppelstunde, 1× gesehen"
    statt „Einzelstunde, 4× gesehen". Aus einem sicheren Muster wurde so ein unsicheres
    mit falscher Länge. Zwei von 686 benachbarten Stundenpaaren im Kollegium waren
    betroffen; die übrigen 684 traten ohnehin gemeinsam auf und verschmelzen weiterhin.

    Ergebnis: (Beginn, Länge, Rhythmus, gesehen).
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
                and stunden[stunde][1] == stunden[vorher][1]
            )
            if not passt:
                bloecke.append(_block(offen, stunden))
                offen = []
        offen.append(stunde)
    if offen:
        bloecke.append(_block(offen, stunden))
    return bloecke


def _block(stunden_liste: list[int], stunden: dict[int, tuple[str, frozenset[int]]]):
    start = stunden_liste[0]
    rhythmus, wochen = stunden[start]
    # Alle Stunden des Blocks teilen dieselbe Wochenmenge — das ist die Bedingung, unter
    # der überhaupt verschmolzen wurde. Ein `min` über die Glieder wäre jetzt ohne
    # Wirkung und würde nur vortäuschen, sie könnten sich unterscheiden.
    return (start, len(stunden_liste), rhythmus, len(wochen))
