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
from sqlalchemy.ext.asyncio import AsyncSession

from app.calendar.patterns import GroupKey
from app.db.models import Group, Subject

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


async def match_groups(db: AsyncSession, keys: list[GroupKey]) -> GroupMatchResult:
    """Abgeglichene und fehlende Unterrichtsgruppen zu den erkannten Lerngruppen.

    Abgeglichen wird über **Fach + Klasse** — dieselbe Kombination, die auch der
    SSO-Gruppenimport als Identität verwendet. Der Gruppenname aus dem Stundenplan taugt
    dafür nicht: Er heißt dort `ET_5_BU` und in der Plattform `Ethik 5b`.
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

    for eintrag in gebuendelt.values():
        subject_id = eintrag["subject_id"]
        art = eintrag["kursart"]
        klassen = eintrag["class_names"]
        slug = await db.scalar(select(Subject.slug).where(Subject.id == subject_id))
        treffer, mehrdeutig = await _vorhandene_gruppe(db, subject_id, klassen, art)
        if mehrdeutig:
            ergebnis.mehrdeutig.append(
                f"{slug} {'/'.join(klassen)}: Es gibt eine Gruppe ohne Angabe der "
                f"Kursart — Basis- und Leistungskurs sind dort nicht zu unterscheiden."
            )
        if treffer is not None:
            ergebnis.vorhanden.extend(eintrag["keys"])
            for k in eintrag["keys"]:
                ergebnis.zuordnung[k] = treffer
            continue

        zusatz = KURSART_LABEL[art]
        name = f"{slug} {'/'.join(klassen)}"
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


async def _vorhandene_gruppe(
    db: AsyncSession,
    subject_id: int,
    class_names: tuple[str, ...],
    art: str = REGULAER,
) -> tuple[int | None, bool]:
    """Passende `teaching_group` und ob die Zuordnung mehrdeutig ist.

    Der Abgleich über den Namen ist grob, aber die einzige verfügbare Brücke: Die
    Plattform speichert bei Unterrichtsgruppen keine Klassenzugehörigkeit, sondern nur
    `subject_id` und einen Namen wie `Mathematik 5c`.

    **In der Kursstufe genügt Fach + Klasse nicht.** Dort gibt es zu einem Fach im selben
    Jahrgang sowohl Basis- als auch Leistungskurs — ein Namenstreffer auf „Biologie 11"
    unterdrückte sonst systematisch einen der beiden Vorschläge. Deshalb muss die Kursart
    im Namen wiederzufinden sein. Fehlt dort jeder Hinweis darauf, ist die Lage
    **mehrdeutig**: Der Vorschlag bleibt stehen und die Unklarheit wird gemeldet, statt
    stillschweigend geraten zu werden.
    """
    kandidaten = await db.execute(
        select(Group.id, Group.name).where(
            Group.type == "teaching_group", Group.subject_id == subject_id
        )
    )
    mehrdeutig = False
    for gruppen_id, name in kandidaten.all():
        klein = (name or "").lower()
        if not any(klasse.lower() in klein for klasse in class_names):
            continue
        if art == REGULAER:
            return gruppen_id, False
        eigene = _KURSART_MARKER[art]
        andere = _KURSART_MARKER[
            LEISTUNGSKURS if art == BASISKURS else BASISKURS
        ]
        if any(marker in klein for marker in eigene):
            return gruppen_id, False
        if any(marker in klein for marker in andere):
            continue                    # die andere Kursart — kein Treffer
        mehrdeutig = True
    return None, mehrdeutig
