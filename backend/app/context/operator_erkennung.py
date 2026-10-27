"""Operator im Satz erkennen — Päckchen AF (0.23), Plan „Operator-im-Satz-AF-Plan".

Eine Aufgabe nennt ihren Operator in Befehlsform am Satzanfang: „Erläutere die Funktion der
Spaltöffnungen", „Werte das Diagramm aus", „Miss die Temperatur". Dieses Modul findet ihn —
als **reine Funktion** über Text und Operator-Titel, ohne Datenbank. Wer die Definition holt
und in den Systemtext setzt, steht in Schritt 3 und 4 des Plans.

**Warum nicht die Nennung der Vorab-Suche** (`nennung.py`): Viele Operatoren sind
Alltagswörter (planen, nutzen, ordnen, *Werte* als Nomen). Als Vorab-Typ brächten sie fast
jeder Nachricht ein Angebot (AE-Plan, S8). Hier zählt deshalb nur die Befehlsform **am
Satzanfang** — dort steht der Operator einer Aufgabenstellung.

**Formen werden abgeleitet, nicht gespeichert** (AE-Plan, S9): Operatoren entstehen nur durch
den Scraper; gepflegte Aliase gingen beim Neuimport verloren.

- *Regelmäßig* über den Wortstamm der Nennung: „Erläutere" → *erläuter* = „erläutern"; auch
  die Sie-Form („Erläutern Sie").
- *Trennbar* über :data:`PARTIKEL`: „Werte das Diagramm aus" = „auswerten" — die Partikel
  steht am Ende des Satzes, eines Teilsatzes vor dem Komma oder vor „und"/„oder".
- *Unregelmäßig* über :data:`AUSNAHMEN`: „Miss", „Gib … an", „Nimm Stellung".

⚠️ **„Erkläre mir …" ist keine Aufgabe** (F5): Steht direkt nach dem Imperativ „mir" oder
„uns", bittet jemand den Assistenten um etwas. Dann zählt der Satz nicht.

⚠️ **Fehltreffer in eine Richtung:** Ein Nomen am Satzanfang („Vergleiche zeigen …") trifft
den Operator wie ein Imperativ. Das kostet einen Definitionsabschnitt im Systemtext, nicht
mehr: Ohne vorgelegte Schülerantwort greift die Prüfregel des Prompts nicht.
"""
import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.context.lookup import normalisiere_titel
from app.context.nennung import stamm

#: Abtrennbare Verbpartikeln, längste zuerst. „an" vor „analysieren" schadet nicht: Ein
#: Verb erhält **beide** Lesarten (untrennbar und getrennt), und „Alysiere … an" schreibt
#: niemand.
PARTIKEL = ("zusammen", "heraus", "wieder", "durch", "fest", "nach", "dar", "her", "vor", "aus",
            "auf", "ein", "mit", "ab", "an", "um", "zu")

#: Unregelmäßige Imperative (Singular) zum Infinitiv. Gilt auch als Wortende: „entwerfen" →
#: „entwirf", „ansehen" getrennt → „sieh … an".
AUSNAHMEN = {
    "messen": "miss", "lesen": "lies", "geben": "gib", "nehmen": "nimm", "sehen": "sieh",
    "sprechen": "sprich", "helfen": "hilf", "werfen": "wirf", "treffen": "triff",
}

#: Wie viele Operatoren eine Nachricht höchstens liefert.
MAX_OPERATOREN = 3

#: Wörter, die eine Bitte an den Assistenten markieren statt einer Aufgabe (F5).
_BITTE = frozenset({"mir", "uns"})

#: Füllwörter in Titeln, die keine Bedingung sind („sich auseinandersetzen", „eine Rolle").
_FUELL = frozenset({"sich", "ein", "eine", "einen", "der", "die", "das", "den", "dem", "und"})

#: Modalverben, mit denen eine Aufgabe berichtet wird: „Das sollen wir erklären."
_AUFTRAG = frozenset({"soll", "sollen", "sollst", "sollt", "muss", "müssen", "musst", "müsst"})

#: Satzgrenzen. Anführungszeichen zählen mit: „In der Aufgabe steht ‚Erkläre den Verlauf'"
#: enthält eine Aufgabe in der Mitte des Satzes.
_SATZ = re.compile(r"[.!?;:\n„“”\"»«‚‘]+")
_WORT = re.compile(r"\w+(?:-\w+)*")
#: Aufzählungszeichen am Satzanfang: „a)", „3b", „Aufgabe 2".
_VORSPANN = re.compile(r"^(?:\d+[a-z]?|[a-z]|aufgabe|teilaufgabe|nr)$")


@dataclass(frozen=True)
class Muster:
    """Eine Lesart eines Operator-Titels."""

    titel: str                       # normalisierter Titel des Knotens
    infinitiv: str                   # „auswerten" — für „Das sollen wir auswerten"
    verb: frozenset[str]             # Stämme, mit denen der Satz beginnen muss
    partikel: str | None             # muss am Ende des Satzes oder eines Teilsatzes stehen
    objekte: tuple[str, ...]         # Stämme, die im Satz vorkommen müssen („Hypothese")

    @property
    def gewicht(self) -> int:
        return (self.partikel is not None) + len(self.objekte)


def _verbformen(verb: str) -> set[str]:
    """Die Stämme, mit denen ein Satz für diesen Infinitiv beginnt (regelmäßig + unregelmäßig)."""
    formen = {stamm(verb)}
    for infinitiv, imperativ in AUSNAHMEN.items():
        if verb.endswith(infinitiv):
            formen.add(stamm(verb[: -len(infinitiv)] + imperativ))
    return formen


def _ist_verb(wort: str) -> bool:
    return len(wort) >= 4 and wort.endswith("n") and wort not in _FUELL


def muster_aus_titel(titel: str) -> list[Muster]:
    """Alle Lesarten eines Titels: je Alternative („beurteilen / Stellung nehmen") und je
    Verb mit Partikel eine untrennbare und eine getrennte."""
    norm = normalisiere_titel(titel)
    ergebnis: list[Muster] = []
    for alternative in norm.split("/"):
        ohne_klammer = re.sub(r"\([^)]*\)", " ", alternative)
        woerter = [w for w in _WORT.findall(ohne_klammer)]
        verben = [i for i, w in enumerate(woerter) if _ist_verb(w)]
        if not verben:
            continue
        # Das Verb ist das letzte Wort auf -n: „Hypothesen aufstellen" → aufstellen. Was
        # davor steht, muss im Satz vorkommen; was danach steht („Stellung nehmen aus der
        # Sicht von …"), ist Ergänzung und keine Bedingung.
        i = verben[-1]
        verb = woerter[i]
        objekte = tuple(stamm(w) for w in woerter[:i] if w not in _FUELL)
        ergebnis.append(Muster(norm, verb, frozenset(_verbformen(verb)), None, objekte))
        for p in PARTIKEL:
            rest = verb[len(p):]
            if verb.startswith(p) and len(rest) >= 4:
                ergebnis.append(Muster(norm, verb, frozenset(_verbformen(rest)), p, objekte))
                break
    return ergebnis


@dataclass
class Operatorindex:
    """Erster Satzstamm → Lesarten, die damit beginnen."""

    nach_verb: dict[str, list[Muster]]
    nach_infinitiv: dict[str, list[Muster]]

    @classmethod
    def aus(cls, titel: Iterable[str]) -> "Operatorindex":
        nach_verb: dict[str, list[Muster]] = {}
        nach_infinitiv: dict[str, list[Muster]] = {}
        for t in titel:
            for m in muster_aus_titel(t):
                for v in m.verb:
                    nach_verb.setdefault(v, []).append(m)
                if m.partikel is None:
                    nach_infinitiv.setdefault(m.infinitiv, []).append(m)
        return cls(nach_verb, nach_infinitiv)


def _saetze(text: str) -> list[list[list[str]]]:
    """Sätze als Liste von Teilsätzen (am Komma), jeder als Liste kleiner Wörter."""
    saetze = []
    for satz in _SATZ.split(text.lower()):
        teile = [_WORT.findall(t) for t in satz.split(",")]
        teile = [t for t in teile if t]
        if teile:
            saetze.append(teile)
    return saetze


def _berichtet(woerter: list[str], index: Operatorindex) -> list[Muster]:
    """„Das sollen wir erklären", „Wir müssen die Messreihe auswerten": der Operator im
    Infinitiv in einem Satz mit Modalverb. Nur der genaue Infinitiv zählt, keine Beugung."""
    if not _AUFTRAG & set(woerter):
        return []
    staemme = {stamm(w) for w in woerter}
    treffer = [m for w in woerter for m in index.nach_infinitiv.get(w, ())
               if all(o in staemme for o in m.objekte)]
    if not treffer:
        return []
    bestes = max(m.gewicht for m in treffer)
    return [m for m in treffer if m.gewicht == bestes]


def erkenne(text: str, index: Operatorindex) -> list[str]:
    """Die Titel der Operatoren, mit denen Sätze in ``text`` beginnen (Imperativ) — oder, nur
    wenn es keinen Imperativ gibt, die ein Satz mit „sollen/müssen" im Infinitiv nennt. In der
    Reihenfolge des Vorkommens, ohne Doppelte, höchstens :data:`MAX_OPERATOREN`.

    ⚠️ **Der Imperativ hat Vorrang** (Lauf 19, O8): „Gib an, welche Stoffe entstehen. … Muss ich
    das noch erklären?" — die Rückfrage nennt *erklären*, die Aufgabe ist *angeben*. Eine
    Aufgabenstellung im Imperativ ist das stärkere Zeichen als ein berichteter Auftrag.
    """
    befohlen: list[str] = []
    berichtet: list[str] = []
    for teile in _saetze(text):
        woerter = [w for t in teile for w in t]
        for m in _berichtet(woerter, index):
            if m.titel not in berichtet:
                berichtet.append(m.titel)
        start = 0
        while start < len(woerter) - 1 and _VORSPANN.match(woerter[start]):
            start += 1
        erstes = woerter[start]
        folgende = woerter[start + 1:start + 3]
        if folgende[:1] and (folgende[0] in _BITTE
                             or (folgende[0] == "sie" and folgende[1:2] and folgende[1] in _BITTE)):
            continue
        # Sie-Form: „Erläutern Sie" — das Pronomen gehört zum Imperativ, nicht zum Satz.
        kandidaten = index.nach_verb.get(stamm(erstes), [])
        if not kandidaten:
            continue
        # Wo eine Partikel stehen kann: am Ende eines Teilsatzes, auch vor „und“/„oder“
        # („Führe den Versuch durch und notiere …“).
        enden = {t[-1] for t in teile} | {
            woerter[j - 1] for j in range(start + 1, len(woerter)) if woerter[j] in ("und", "oder")}
        staemme = {stamm(w) for w in woerter[start + 1:]}
        passend = [m for m in kandidaten
                   if (m.partikel is None or m.partikel in enden)
                   and all(o in staemme for o in m.objekte)]
        if not passend:
            continue
        bestes = max(m.gewicht for m in passend)
        for m in passend:
            if m.gewicht == bestes and m.titel not in befohlen:
                befohlen.append(m.titel)
    return (befohlen or berichtet)[:MAX_OPERATOREN]
