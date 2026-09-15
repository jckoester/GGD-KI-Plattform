"""Unterrichtsgruppen aus dem Stundenplan vorschlagen (UP-8, Schritt 7).

Der Stundenplan nennt Fach, Klasse und Lehrkraft — daraus lassen sich fehlende
`teaching_group`-Einträge vorschlagen. Vorgeschlagen wird nur, was **fehlt**; vorhandene
Gruppen bleiben unangetastet.

**Nicht auflösbare Fächer werden gemeldet, nicht übersprungen.** Ein Fach, das die
Plattform nicht kennt, ist der häufigste Grund, warum eine Gruppe fehlt — es still
auszulassen hieße, den Anwender mit einer unerklärlichen Lücke sitzen zu lassen.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.calendar.patterns import GroupKey
from app.db.models import Group, GroupMembership, Subject

logger = logging.getLogger(__name__)

# Kurse desselben Fachs tragen im Stundenplan angehängte Ziffern: M1, M2, bio2, e1, g3.
# Für die Fachzuordnung sind sie bedeutungslos — die Gruppe unterscheidet die Klasse.
_KURS_ZIFFER = re.compile(r"\d+$")


def kein_unterricht_codes() -> frozenset[str]:
    """Stundenplan-Kürzel, hinter denen kein Unterricht steht.

    Aus `config/subjects.yaml` (`untis_kein_unterricht`), weil es schulspezifisch ist: Am
    GGD sind das Präsenzstunden, Personalrats- und Schulleitungssitzungen.

    **Der Unterschied zu einem unbekannten Kürzel ist der Handlungsbedarf.** Ein
    unbekanntes Fach heißt: Hier fehlt ein Eintrag. Ein Diensttermin heißt: Hier fehlt
    nichts. Beides gleich zu melden hieße, die Lehrkraft dauerhaft mit etwas zu
    behelligen, das nie fertig wird — und die echten Lücken darin untergehen zu lassen.
    """
    from app.context.editions import load_subjects_config

    try:
        roh = load_subjects_config().get("untis_kein_unterricht") or []
    except (OSError, ValueError):
        logger.warning("subjects.yaml nicht lesbar — keine Nicht-Unterricht-Liste")
        return frozenset()
    return frozenset(str(code).strip().upper() for code in roh if str(code).strip())


def code_varianten(code: str) -> list[str]:
    """Schreibweisen eines Stundenplan-Kürzels — **nur für die Fachauflösung**.

    Für die Frage „welches Fach ist das?" ist die Groß-/Kleinschreibung bedeutungslos:
    `bio` und `BIO` sind beide Biologie. Für die Frage „welche Lerngruppe ist das?" ist sie
    es **nicht** — siehe `kursart()`. Diese Funktion beantwortet nur die erste.

    Ziffern kennzeichnen Parallelkurse (`M1`, `M2`, `bio2`, `e1`, `g3`) und sind fürs Fach
    ebenfalls ohne Belang. Deshalb erst exakt, dann ohne angehängte Ziffern — in dieser
    Reihenfolge, damit ein Fach, das tatsächlich auf eine Ziffer endet (`L2` = zweite
    Fremdsprache), zuerst exakt trifft.
    """
    gross = code.strip().upper()
    varianten = [gross]
    ohne_ziffer = _KURS_ZIFFER.sub("", gross)
    if ohne_ziffer and ohne_ziffer != gross:
        varianten.append(ohne_ziffer)
    return varianten


# Kursstufe: Klassenbezeichnung ohne Buchstabensuffix (`11`, `12`) — Sek I trägt immer
# einen (`5A` … `10D`). `J1`/`K1` als verbreitete Schreibweisen mit abgedeckt.
_KURSSTUFE = re.compile(r"^(?:[JK]\s*)?\d{1,2}$", re.IGNORECASE)

REGULAER = "regulaer"
BASISKURS = "basiskurs"
LEISTUNGSKURS = "leistungskurs"

KURSART_LABEL = {
    REGULAER: "",
    BASISKURS: "Basiskurs",
    LEISTUNGSKURS: "Leistungskurs",
}


def ist_kursstufe(class_names: tuple[str, ...]) -> bool:
    """Ob die Klassenbezeichnungen auf die Kursstufe deuten.

    Belegt an den echten Daten: Sek-I-Klassen heißen `5A` bis `10D` — immer mit
    Buchstabensuffix. Die Kursstufe heißt schlicht `11` und `12`.
    """
    return bool(class_names) and all(
        _KURSSTUFE.match(name.strip()) for name in class_names
    )


def kursart(code: str, class_names: tuple[str, ...]) -> str:
    """Basiskurs, Leistungskurs oder regulärer Unterricht.

    **Die Groß-/Kleinschreibung des Fachkürzels trägt Bedeutung** — sie ist keine
    Nachlässigkeit in der Pflege:

    * **klein** → Basiskurs der Kursstufe (`bio`, `m1`, `ph`, `g3`)
    * **groß** → Leistungskurs der Kursstufe, oder regulärer Unterricht in Unter- und
      Mittelstufe (`BIO`, `M`, `BK`)

    Das ist für die Gruppenzuordnung entscheidend: Basis- und Leistungskurs desselben
    Fachs im selben Jahrgang sind **verschiedene** Unterrichtsgruppen. Wer hier
    normalisiert, wirft sie zusammen.

    In der Aufzeichnung vom 06.08.2026 kamen kleingeschriebene Kürzel **ausschließlich**
    mit den Klassen 11 und 12 vor — die Regel deckt sich also mit den Daten.
    """
    if not ist_kursstufe(class_names):
        return REGULAER
    bereinigt = code.strip()
    return BASISKURS if bereinigt != bereinigt.upper() else LEISTUNGSKURS


async def resolve_subject(db: AsyncSession, code: str) -> int | None:
    """Stundenplan-Kürzel → `subjects.id`, oder None.

    Gesucht wird in `subjects.untis_codes` — einem **eigenen** Vokabular. Der Abgleich am
    06.08.2026 zeigte, warum: Von elf Kürzeln löste sich eines über den Slug auf und zwei
    über `fach_code`. `ETH` ≠ `ET`, `INFWFO` ≠ `INF`.

    Als Rückfall danach `fach_code` und der Slug — für Fächer, deren Stundenplan-Kürzel
    zufällig übereinstimmt und deshalb nicht eigens eingetragen wurde.
    """
    for variante in code_varianten(code):
        treffer = await db.scalar(
            select(Subject.id).where(Subject.untis_codes.any(variante)).limit(1)
        )
        if treffer:
            return treffer
    for variante in code_varianten(code):
        treffer = await db.scalar(
            select(Subject.id)
            .where(func.upper(Subject.fach_code) == variante)
            .limit(1)
        )
        if treffer:
            return treffer
        treffer = await db.scalar(
            select(Subject.id).where(func.lower(Subject.slug) == variante.lower()).limit(1)
        )
        if treffer:
            return treffer
    return None


@dataclass
class GroupSuggestion:
    """Eine Unterrichtsgruppe, die es in der Plattform noch nicht gibt.

    `keys` kann **mehrere** Lerngruppen-Schlüssel umfassen: Ein Fach kann in einer Klasse
    unter mehreren Stundenplan-Kürzeln laufen (`M` und `MD`, `D` und `DD`, `E` und `ED`)
    und ist trotzdem **eine** Gruppe — siehe `_gruppenidentitaet`.
    """

    keys: tuple[GroupKey, ...]
    codes: tuple[str, ...]           # die Fachkürzel dahinter, z. B. ('M', 'MD')
    subject_id: int
    subject_slug: str
    class_names: tuple[str, ...]
    stunden: int                     # wie oft im Abrufzeitraum gesehen
    vorschlag_name: str
    kursart: str = REGULAER

    @property
    def key(self) -> GroupKey:
        """Der erste Schlüssel — für Aufrufer, die nur einen brauchen."""
        return self.keys[0]


@dataclass
class UnresolvedSubject:
    """Ein Fachkürzel, das die Plattform nicht kennt."""

    code: str
    stunden: int
    klassen: tuple[str, ...]


@dataclass
class GroupMatchResult:
    vorhanden: list[GroupKey] = field(default_factory=list)
    fehlend: list[GroupSuggestion] = field(default_factory=list)
    unbekannte_faecher: list[UnresolvedSubject] = field(default_factory=list)
    ohne_klasse: list[str] = field(default_factory=list)
    # Lerngruppen-Schlüssel → `groups.id` der vorhandenen Unterrichtsgruppe. Erst damit
    # lassen sich Stunden auf Slots abbilden (Schritt 8) — ohne die ID ist „vorhanden"
    # nur eine Feststellung.
    zuordnung: dict[GroupKey, int] = field(default_factory=dict)
    # Kursstufen-Gruppen, bei denen sich Basis- und Leistungskurs nicht auseinanderhalten
    # lassen, weil der vorhandene Gruppenname die Kursart nicht nennt.
    mehrdeutig: list[str] = field(default_factory=list)


def _gruppenidentitaet(
    key: GroupKey, subject_id: int, art: str
) -> tuple:
    """Woran sich entscheidet, ob zwei Stunden **dieselbe** Lerngruppe sind.

    Belegt an der Aufzeichnung vom 06.08.2026 (1218 Stunden, 90 Lehrkräfte):

    * **Mit `studentGroup`** ist diese die Identität. Sie unterscheidet, was sonst
      ununterscheidbar wäre: `SPM_7_RO` und `SPW_7_GÜN` sind beide Sport in 7A+7D, aber
      zwei Gruppen (männlich/weiblich). **Jede** Kursstufen-Stunde trägt eine.
    * **Ohne `studentGroup`** ist es der reguläre Klassenunterricht — dann zählt Fach +
      Klasse, **nicht** das Kürzel. Denn dasselbe Fach läuft in einer Klasse unter
      mehreren Kürzeln: `M` und `MD` (Differenzierung), `D`/`DD`, `E`/`ED`. Das ist
      **eine** Gruppe mit demselben Curriculum; die Differenzierungsstunde ist eine
      weitere Stunde derselben Gruppe, keine zweite Gruppe.

    Ohne diese Unterscheidung entstünde entweder eine Dublette (M/MD getrennt) oder eine
    Verschmelzung zweier echter Gruppen (SPM/SPW zusammen) — je nachdem, welche Seite man
    vereinfacht.
    """
    if key.student_group:
        return ("sg", key.student_group)
    return ("fach", subject_id, key.class_names, art)


async def match_groups(
    db: AsyncSession, keys: list[GroupKey], *, pseudonym: str
) -> GroupMatchResult:
    """Abgeglichene und fehlende Unterrichtsgruppen zu den erkannten Lerngruppen.

    Abgeglichen wird über **Fach + Klasse** — dieselbe Kombination, die auch der
    SSO-Gruppenimport als Identität verwendet. Der Gruppenname aus dem Stundenplan taugt
    dafür nicht: Er heißt dort `ET_5_BU` und in der Plattform `Ethik 5b`.

    `pseudonym` ist keine Nebensache und deshalb ein Pflichtargument: Gesucht wird
    ausschließlich unter den **eigenen** Unterrichtsgruppen. Bis zum 15.09.2026 lief die
    Suche schulweit — ein Vorschlag konnte auf die Gruppe einer Kollegin zeigen, und der
    tägliche Abgleich hätte Entfall und Vertretung in deren Jahresplanung geschrieben.
    """
    ergebnis = GroupMatchResult()
    unbekannt: dict[str, list[GroupKey]] = {}
    haeufigkeit = Counter(key for key in keys)
    # Identität → alles, was zu dieser einen Gruppe gehört
    gebuendelt: dict[tuple, dict] = {}

    for key in sorted(set(keys), key=lambda k: k.label):
        if not key.subject:
            # Ohne Fach ist keine Zuordnung möglich; das ist etwas anderes als ein
            # unbekanntes Fach und wird getrennt gemeldet.
            ergebnis.ohne_klasse.append(key.label)
            continue

        subject_id = await resolve_subject(db, key.subject)
        if subject_id is None:
            unbekannt.setdefault(key.subject.strip().upper(), []).append(key)
            continue
        if not key.class_names:
            ergebnis.ohne_klasse.append(key.label)
            continue

        art = kursart(key.subject, key.class_names)
        identitaet = _gruppenidentitaet(key, subject_id, art)
        eintrag = gebuendelt.setdefault(
            identitaet,
            {"keys": [], "codes": [], "subject_id": subject_id, "kursart": art,
             "class_names": key.class_names, "stunden": 0},
        )
        eintrag["keys"].append(key)
        eintrag["codes"].append(key.subject.strip())
        eintrag["stunden"] += haeufigkeit[key]
        # Die längste Klassenliste gewinnt — bei M/MD sind sie gleich, bei
        # zusammengelegten Gruppen ist die vollständigere die richtige.
        if len(key.class_names) > len(eintrag["class_names"]):
            eintrag["class_names"] = key.class_names

    eintraege = list(gebuendelt.values())
    kandidaten = await _eigene_gruppen(db, pseudonym)
    treffer, rest = zuordnen(
        [(e["subject_id"], e["class_names"], e["kursart"]) for e in eintraege],
        kandidaten,
    )

    for i, eintrag in enumerate(eintraege):
        subject_id = eintrag["subject_id"]
        art = eintrag["kursart"]
        klassen = eintrag["class_names"]
        slug = await db.scalar(select(Subject.slug).where(Subject.id == subject_id))
        name = f"{slug} {'/'.join(klassen)}"

        if i in treffer:
            ergebnis.vorhanden.extend(eintrag["keys"])
            for k in eintrag["keys"]:
                ergebnis.zuordnung[k] = treffer[i]
            continue

        # Kandidaten, aber keine Entscheidung: melden statt raten. Der Vorschlag bleibt
        # daneben stehen — welche der beiden Lesarten stimmt, weiß nur die Lehrkraft.
        if rest.get(i):
            ergebnis.mehrdeutig.append(
                f"{name}: keine eindeutige Zuordnung — infrage kommen "
                + ", ".join(f"„{k.name}“" for k in rest[i])
                + ". Bitte von Hand zuordnen."
            )

        zusatz = KURSART_LABEL[art]
        ergebnis.fehlend.append(
            GroupSuggestion(
                keys=tuple(eintrag["keys"]),
                codes=tuple(sorted(set(eintrag["codes"]))),
                subject_id=subject_id,
                subject_slug=slug or "",
                class_names=klassen,
                stunden=eintrag["stunden"],
                vorschlag_name=f"{name} ({zusatz})" if zusatz else name,
                kursart=art,
            )
        )

    for code, betroffene in sorted(unbekannt.items()):
        ergebnis.unbekannte_faecher.append(
            UnresolvedSubject(
                code=code,
                stunden=sum(haeufigkeit[k] for k in betroffene),
                klassen=tuple(
                    sorted({name for k in betroffene for name in k.class_names})
                ),
            )
        )
    _namen_eindeutig_machen(ergebnis.fehlend)
    return ergebnis


def _namen_eindeutig_machen(vorschlaege: list[GroupSuggestion]) -> None:
    """Gleichnamige Vorschläge um ihr Stundenplan-Kürzel ergänzen.

    Ein Fach kann zu derselben Klasse mehrere Lerngruppen führen, ohne dass Fach, Klasse
    oder Kursart sie unterscheiden. Belegt: **`SPM` und `SPW`** — Sport männlich und
    weiblich, dasselbe Fach, dieselbe Klasse, zwei Gruppen. Beide hießen sonst „sport 7A",
    und die Lehrkraft müsste raten, welche welche ist.

    Bewusst kollisionsgetrieben statt als Sonderfall für Sport: Welche Unterscheidungen
    eine Schule im Stundenplan führt, ist nicht vorhersehbar. Was sich am Namen nicht
    unterscheidet, bekommt das Kürzel angehängt — das ist immer korrekt und nie im Weg.
    """
    haeufigkeit = Counter(v.vorschlag_name for v in vorschlaege)
    for vorschlag in vorschlaege:
        if haeufigkeit[vorschlag.vorschlag_name] > 1 and vorschlag.key.subject:
            vorschlag.vorschlag_name = (
                f"{vorschlag.vorschlag_name} [{vorschlag.key.subject.strip()}]"
            )


# Wörter, an denen sich die Kursart im Gruppennamen erkennen lässt.
_KURSART_MARKER = {
    BASISKURS: ("basiskurs", "basis", "bk"),
    LEISTUNGSKURS: ("leistungskurs", "leistung", "lk"),
}


@dataclass(frozen=True)
class Kandidat:
    """Eine eigene Unterrichtsgruppe, wie sie für die Zuordnung gebraucht wird."""

    id: int
    name: str
    subject_id: int
    quellklasse: str | None     # Name der Klasse, aus der die Gruppe entstanden ist


async def _eigene_gruppen(db: AsyncSession, pseudonym: str) -> list[Kandidat]:
    """Alle Unterrichtsgruppen, in denen die Lehrkraft selbst als `teacher` steht.

    Einmal geladen, nicht je Fach: Die Zuordnung braucht den Gesamtblick, weil sie
    Eindeutigkeit **von beiden Seiten** prüft. Dieselbe Bedingung wie in
    `require_group_teacher` — wo die Lehrkraft nicht schreiben dürfte, darf auch kein
    Vorschlag hinzeigen.
    """
    quelle = aliased(Group)
    zeilen = await db.execute(
        select(Group.id, Group.name, Group.subject_id, quelle.name)
        .join(GroupMembership, GroupMembership.group_id == Group.id)
        .outerjoin(quelle, quelle.id == Group.source_class_group_id)
        .where(
            Group.type == "teaching_group",
            GroupMembership.pseudonym == pseudonym,
            GroupMembership.role_in_group == "teacher",
        )
    )
    return [
        Kandidat(id=gid, name=name or "", subject_id=sid, quellklasse=quellname)
        for gid, name, sid, quellname in zeilen.all()
    ]


def _widerspricht_kursart(name: str, art: str) -> bool:
    """Ob der Gruppenname die **andere** Kursart nennt.

    Nur dann ist ein Treffer ausgeschlossen. Nennt der Name gar keine Kursart, bleibt die
    Gruppe Kandidatin — ob das eindeutig ist, entscheidet das Verfahren, nicht der Name.
    """
    if art == REGULAER:
        return False
    klein = (name or "").lower()
    if any(marker in klein for marker in _KURSART_MARKER[art]):
        return False
    andere = _KURSART_MARKER[LEISTUNGSKURS if art == BASISKURS else BASISKURS]
    return any(marker in klein for marker in andere)


def _nennt_klasse(kandidat: Kandidat, class_names: tuple[str, ...]) -> bool:
    """Ob Gruppenname **oder** Quellklasse eine der Klassen aus dem Stundenplan nennt.

    Die Quellklasse ist der belastbarere Weg — sie ist ein Fremdschlüssel, kein Text. Der
    Name bleibt daneben stehen, weil Gruppen aus dem Schulkonto keine Quellklasse haben.
    """
    name = kandidat.name.lower()
    quelle = (kandidat.quellklasse or "").lower()
    return any(
        klasse.lower() in name or (quelle and klasse.lower() in quelle)
        for klasse in class_names
    )


def _eindeutige_paare(
    kanten: dict[int, set[int]],
    offen_l: set[int],
    offen_g: set[int],
    zuordnung: dict[int, int],
) -> None:
    """Paare zuordnen, die **von beiden Seiten** nur einen Partner haben — bis nichts mehr geht.

    Von beiden Seiten, weil eine Lerngruppe ohne Gruppe erlaubt ist: Aus „diese Lerngruppe
    hat nur einen Kandidaten" folgt deshalb **nicht**, dass sie ihn nehmen muss. Eine
    Lehrkraft mit einer Chemie-Gruppe und zwei Chemie-Kursen im Stundenplan bekäme sonst
    beide auf dieselbe Gruppe gelegt.

    Wiederholt, weil mehrere Paare **gleichzeitig** eindeutig sein können und die innere
    Schleife nach jedem Treffer abbricht — sie verändert die Mengen, über die sie läuft.
    Ohne die Wiederholung bliebe es bei einem Paar je Durchgang; eine Lehrkraft mit drei
    über den Namen erkennbaren Gruppen bekäme nur zwei zugeordnet.

    Ein zugeordnetes Paar kann dagegen **kein** weiteres eindeutig machen: Die Lerngruppe
    hatte nur diesen einen Kandidaten und war damit selbst die einzige Bewerberin um ihn —
    an den übrigen Mengen ändert ihr Wegfall nichts. Wo etwas aufgeht, das vorher
    mehrdeutig war, liegt es an der **Reihenfolge der Durchgänge**: Eine starke Kante ist
    unter den starken Kanten eindeutig, im vollen Graphen oft nicht.
    """
    while True:
        moeglich = {i: kanten[i] & offen_g for i in offen_l}
        for i, kandidaten in moeglich.items():
            if len(kandidaten) != 1:
                continue
            j = next(iter(kandidaten))
            if sum(1 for k in offen_l if j in moeglich[k]) != 1:
                continue        # mehrere Lerngruppen wollen dieselbe Gruppe
            zuordnung[i] = j
            offen_l.discard(i)
            offen_g.discard(j)
            break
        else:
            return


def zuordnen(
    lerngruppen: list[tuple[int, tuple[str, ...], str]],
    kandidaten: list[Kandidat],
) -> tuple[dict[int, int], dict[int, list[Kandidat]]]:
    """Lerngruppen aus dem Stundenplan den eigenen Unterrichtsgruppen zuordnen.

    `lerngruppen` sind Tripel aus `subject_id`, Klassennamen und Kursart.

    Bis zum 15.09.2026 entschied allein der Gruppen**name**: Eine Gruppe galt als Treffer,
    wenn einer der Klassennamen aus dem Stundenplan darin vorkam. In der Kursstufe geht
    das nicht auf — der Stundenplan nennt die „Klasse" `11`, die Gruppe heißt
    `ch2-ks-abi28`. Gemessen an der Produktion (14.09.2026) traf das fünf von sechs
    Lerngruppen und scheiterte genau am Kursstufenkurs.

    Stattdessen: Das **Fach** trägt die Zuordnung, der Name schärft sie.

    1. Kanten zwischen jeder Lerngruppe und jeder eigenen Gruppe desselben Fachs.
    2. Kanten streichen, die der Kursart widersprechen.
    3. **Starke** Kanten zuerst — Klassenname im Gruppennamen oder in der Quellklasse.
    4. Dann der Rest, jeweils nur bei Eindeutigkeit von beiden Seiten.

    Ergebnis: Zuordnung (Index der Lerngruppe → `groups.id`) und, für alles Übrige, die
    Kandidaten, die noch infrage kämen. Leer heißt „keine Gruppe vorhanden", mehrere heißen
    „nicht auflösbar" — geraten wird in keinem Fall.
    """
    kanten: dict[int, set[int]] = {}
    starke: dict[int, set[int]] = {}
    for i, (subject_id, class_names, art) in enumerate(lerngruppen):
        moeglich: set[int] = set()
        deutlich: set[int] = set()
        for j, kandidat in enumerate(kandidaten):
            if kandidat.subject_id != subject_id:
                continue
            if _widerspricht_kursart(kandidat.name, art):
                continue
            moeglich.add(j)
            if _nennt_klasse(kandidat, class_names):
                deutlich.add(j)
        kanten[i] = moeglich
        starke[i] = deutlich

    zuordnung: dict[int, int] = {}
    offen_l = set(kanten)
    offen_g = set(range(len(kandidaten)))
    for menge in (starke, kanten):
        _eindeutige_paare(menge, offen_l, offen_g, zuordnung)

    rest = {
        i: [kandidaten[j] for j in sorted(kanten[i] & offen_g)] for i in sorted(offen_l)
    }
    return {i: kandidaten[j].id for i, j in zuordnung.items()}, rest
