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
from app.db.models import Group, GroupMembership, GroupSourceClass, Subject

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
#
# Gesucht wird an **Wortgrenzen**, nicht als Teilzeichenkette. Als Teilzeichenkette fand
# `lk` sich in „Volkskunde" und `bk` in „Werkbank" — und ein falsch erkannter Marker
# streicht eine gültige Kante, der Kurs findet seine Gruppe dann nicht mehr.
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
    # Namen **aller** Klassen, aus denen die Gruppe entstanden ist (Alembic 0068).
    # Mehrzahl, seit eine Gruppe aus mehreren Klassenverbänden stammen kann.
    quellklassen: tuple[str, ...] = ()
    fach_code: str | None = None    # Fachkürzel — kollidiert mit den Kursart-Markern


async def _eigene_gruppen(db: AsyncSession, pseudonym: str) -> list[Kandidat]:
    """Alle Unterrichtsgruppen, in denen die Lehrkraft selbst als `teacher` steht.

    Einmal geladen, nicht je Fach: Die Zuordnung braucht den Gesamtblick, weil sie
    Eindeutigkeit **von beiden Seiten** prüft. Dieselbe Bedingung wie in
    `require_group_teacher` — wo die Lehrkraft nicht schreiben dürfte, darf auch kein
    Vorschlag hinzeigen.
    """
    quelle = aliased(Group)
    zeilen = await db.execute(
        select(Group.id, Group.name, Group.subject_id, quelle.name, Subject.fach_code)
        .join(GroupMembership, GroupMembership.group_id == Group.id)
        # Eine Gruppe kann aus mehreren Klassen stammen: Der Join vervielfacht die Zeile
        # entsprechend, unten werden die Klassennamen je Gruppe wieder eingesammelt.
        .outerjoin(GroupSourceClass, GroupSourceClass.group_id == Group.id)
        .outerjoin(quelle, quelle.id == GroupSourceClass.class_group_id)
        .outerjoin(Subject, Subject.id == Group.subject_id)
        .where(
            Group.type == "teaching_group",
            GroupMembership.pseudonym == pseudonym,
            GroupMembership.role_in_group == "teacher",
        )
    )
    # `Kandidat` ist frozen — erst die Klassennamen je Gruppe sammeln, dann bauen.
    rohdaten: dict[int, tuple[str, int | None, str | None]] = {}
    klassen: dict[int, set[str]] = {}
    for gid, name, sid, quellname, fach_code in zeilen.all():
        rohdaten.setdefault(gid, (name or "", sid, fach_code))
        if quellname:
            klassen.setdefault(gid, set()).add(quellname)
    return [
        Kandidat(
            id=gid,
            name=name,
            subject_id=sid,
            fach_code=fach_code,
            # Sortiert, damit dieselbe Gruppe über Läufe hinweg dieselbe Reihenfolge
            # trägt — die Zuordnung darf nicht von der Zeilenfolge der DB abhängen.
            quellklassen=tuple(sorted(klassen.get(gid, ()))),
        )
        for gid, (name, sid, fach_code) in rohdaten.items()
    ]


def _ohne_fachkuerzel(name: str, fach_code: str | None) -> str:
    """Das eigene Fachkürzel aus dem Namen nehmen, bevor nach Kursart-Markern gesucht wird.

    `BK` ist das Fachkürzel für Bildende Kunst **und** die Kurzform für Basiskurs. Eine
    Kursstufen-Gruppe namens „BK 11" las sich deshalb als Basiskurs — und war sie in
    Wahrheit der Leistungskurs, wurde ihre Kante gestrichen und der Kurs fand seine Gruppe
    nicht. Dasselbe gilt für `LK` in Sprachen, die so abgekürzt werden.

    Das Kürzel der Gruppe steht fest (sie hängt an genau einem Fach), also lässt sich die
    Doppeldeutigkeit auflösen, statt sie zu erraten: Steht `BK` im Namen einer
    BK-Gruppe, ist es das Fach. Bei „Bio BK 11" bleibt `bk` stehen und zählt als Marker.
    """
    if not fach_code:
        return name
    return re.sub(rf"\b{re.escape(fach_code)}\b", " ", name, flags=re.IGNORECASE)


def _nennt_kursart(name: str, art: str) -> bool:
    return any(
        re.search(rf"\b{marker}\b", name) for marker in _KURSART_MARKER[art]
    )


def _widerspricht_kursart(name: str, art: str, fach_code: str | None = None) -> bool:
    """Ob der Gruppenname die **andere** Kursart nennt.

    Nur dann ist ein Treffer ausgeschlossen. Nennt der Name gar keine Kursart, bleibt die
    Gruppe Kandidatin — ob das eindeutig ist, entscheidet das Verfahren, nicht der Name.

    Bewusst zurückhaltend: Ein **falsch erkannter** Marker streicht eine gültige Kante, und
    der Kurs erscheint danach als „Gruppe fehlt". Ein **übersehener** Marker lässt die
    Gruppe nur Kandidatin bleiben; bleibt es dann mehrdeutig, wird das gemeldet. Seit der
    beidseitig eindeutigen Zuordnung (15.09.2026) ist das zweite Versagen deutlich
    harmloser als das erste — deshalb im Zweifel nicht streichen.
    """
    if art == REGULAER:
        return False
    klein = _ohne_fachkuerzel(name or "", fach_code).lower()
    if _nennt_kursart(klein, art):
        return False
    return _nennt_kursart(klein, LEISTUNGSKURS if art == BASISKURS else BASISKURS)


def _nennt_klasse(kandidat: Kandidat, class_names: tuple[str, ...]) -> bool:
    """Ob Gruppenname **oder** eine der Quellklassen eine Klasse aus dem Stundenplan nennt.

    Die Quellklassen sind der belastbarere Weg — sie sind Fremdschlüssel, kein Text. Der
    Name bleibt daneben stehen, weil Gruppen aus dem Schulkonto keine Quellklasse haben.

    ⚠️ **Es genügt *eine* passende Quellklasse.** Eine Gruppe aus 10a/10b/10c soll auch
    dann als „nennt die Klasse" gelten, wenn der Stundenplan nur die 10b nennt — sonst
    verlöre genau die mehrklassige Gruppe ihre starke Kante und fiele in die schwächere
    Eindeutigkeitsrunde zurück.
    """
    name = kandidat.name.lower()
    quellen = [q.lower() for q in kandidat.quellklassen]
    return any(
        klasse.lower() in name or any(klasse.lower() in q for q in quellen)
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
            if _widerspricht_kursart(kandidat.name, art, kandidat.fach_code):
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


@dataclass
class Klassenaufloesung:
    """Welche Klassennamen des Stundenplans auf Klassengruppen der Plattform passen."""

    treffer: dict[str, int]            # Klassenname → `groups.id`
    ohne_treffer: tuple[str, ...]      # genannt, aber auf der Plattform nicht vorhanden
    kursstufe: bool

    @property
    def mehrklassig(self) -> bool:
        """Über mehrere Klassen hinweg — also eine **Auswahl** aus diesen Klassen."""
        return len(self.treffer) > 1

    @property
    def erbt(self) -> bool:
        """Ob die Gruppe ihre Mitglieder aus der Klasse bekommt.

        ⚠️ **Nur bei genau einer Klasse** (Entscheidung Jan, 23.09.2026). Eine Gruppe
        über mehreren Klassen ist per Konstruktion eine Auswahl daraus — sonst würde sie
        je Klasse unterrichtet. Sie zu befüllen hieße, Schüler:innen in eine Gruppe zu
        schreiben, in der sie nicht sind.
        """
        return not self.kursstufe and len(self.treffer) == 1


async def klassenkarte(db: AsyncSession) -> dict[str, int]:
    """Alle Klassengruppen als `name.lower() → id`. Einmal laden, oft fragen."""
    zeilen = await db.execute(
        select(Group.id, Group.name).where(Group.type == "school_class")
    )
    return {(name or "").strip().lower(): gid for gid, name in zeilen.all()}


def quellklassen_aufloesen(
    karte: dict[str, int], class_names: tuple[str, ...]
) -> Klassenaufloesung:
    """Aus Klassennamen des Stundenplans die Quellklassen der Gruppe bestimmen.

    ⚠️ **In der Kursstufe wird bewusst nicht gesucht.** Dort heißt die „Klasse" `11` oder
    `J1` und bezeichnet einen ganzen Jahrgang; eine Vererbung daraus schriebe den
    kompletten Jahrgang in einen Kurs von zwanzig Leuten. Solche Gruppen leben vom
    Beitrittscode. Entsprechend ist dort auch nichts „ohne Treffer" — es wurde nichts
    gesucht, also fehlt auch nichts.

    Rein, ohne Datenbank: Dieselbe Antwort braucht die Vorschlagsliste (*woher kämen die
    Mitglieder?*) und die Anlage (*was wird verknüpft?*). Zwei Rechnungen liefen
    auseinander, und die Liste verspräche etwas, das die Anlage nicht hält.
    """
    if ist_kursstufe(class_names):
        return Klassenaufloesung(treffer={}, ohne_treffer=(), kursstufe=True)
    treffer = {}
    for roh in class_names:
        klassen_id = karte.get(roh.strip().lower())
        if klassen_id is not None:
            treffer[roh] = klassen_id
    return Klassenaufloesung(
        treffer=treffer,
        ohne_treffer=tuple(n for n in class_names if n not in treffer),
        kursstufe=False,
    )


@dataclass
class Anlageergebnis:
    """Was beim Anlegen einer Gruppe aus dem Stundenplan herauskam."""

    group_id: int
    name: str
    subject_id: int
    quellklassen: tuple[str, ...]      # tatsächlich verknüpfte Klassen (Herkunft)
    ohne_treffer: tuple[str, ...]      # im Stundenplan genannt, auf der Plattform nicht
    kursstufe: bool
    # Ob die Gruppe ihre Mitglieder aus der Klasse bekommt — nur bei genau einer.
    erbt: bool = False


async def lege_gruppe_aus_vorschlag_an(
    db: AsyncSession, vorschlag: GroupSuggestion, pseudonym: str
) -> Anlageergebnis:
    """Aus einem Stundenplan-Vorschlag eine Unterrichtsgruppe machen.

    ⚠️ **Der Aufrufer hat die Berechtigung bereits geprüft.** Diese Funktion glaubt dem
    `vorschlag` — er muss aus einem serverseitigen Abgleich stammen, nicht aus der
    Anfrage. Wer hier einen selbstgebauten `GroupSuggestion` hineinreicht, legt eine
    beliebige Gruppe an.

    **Quellklassen nur im Klassenverband.** Die Klassennamen aus dem Stundenplan werden
    auf `school_class`-Gruppen abgebildet; wo eine passt, erbt die Gruppe von dort
    (`group_source_classes`). In der **Kursstufe** wird das bewusst übersprungen: Dort
    heißt die „Klasse" `11` oder `J1` und bezeichnet einen ganzen Jahrgang. Eine
    Vererbung daraus schriebe den kompletten Jahrgang in einen Kurs von zwanzig Leuten.
    Solche Gruppen leben vom Beitrittscode.

    Nicht gefundene Klassen sind **kein Fehler**: Die Gruppe entsteht trotzdem und die
    Lücke wird gemeldet. Sonst scheiterte das Anlegen an einer Klasse, die auf der
    Plattform schlicht noch nicht existiert — und die Lehrkraft stünde ohne Gruppe da.
    """
    karte = await klassenkarte(db)
    aufloesung = quellklassen_aufloesen(karte, vorschlag.class_names)
    kursstufe, treffer, ohne_treffer = (
        aufloesung.kursstufe, aufloesung.treffer, aufloesung.ohne_treffer
    )

    basis = f"teaching-{vorschlag.subject_slug}-{_slugteil(vorschlag.vorschlag_name)}"
    slug = basis
    lauf = 1
    while (await db.execute(select(Group.id).where(Group.slug == slug))).scalar_one_or_none():
        slug = f"{basis}-{lauf}"
        lauf += 1

    gruppe = Group(
        name=vorschlag.vorschlag_name,
        slug=slug,
        type="teaching_group",
        subject_id=vorschlag.subject_id,
        sso_group_id=None,
    )
    db.add(gruppe)
    await db.flush()

    for klassen_id in dict.fromkeys(treffer.values()):
        db.add(GroupSourceClass(group_id=gruppe.id, class_group_id=klassen_id))

    db.add(
        GroupMembership(
            group_id=gruppe.id,
            pseudonym=pseudonym,
            role_in_group="teacher",
            # Die Mitgliedschaft ist der Nachweis, dass die Gruppe ihr gehört.
            herkunft="eigen",
        )
    )
    await db.flush()

    return Anlageergebnis(
        group_id=gruppe.id,
        name=gruppe.name,
        subject_id=vorschlag.subject_id,
        quellklassen=tuple(treffer),
        ohne_treffer=ohne_treffer,
        kursstufe=kursstufe,
        erbt=aufloesung.erbt,
    )


def _slugteil(text: str) -> str:
    """Ein Gruppenname als Slug-Bestandteil — klein, ohne Sonderzeichen."""
    klein = text.strip().lower()
    ersetzt = re.sub(r"[^a-z0-9]+", "-", klein.translate(
        str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
    ))
    return ersetzt.strip("-") or "gruppe"
