"""Nachschlagen benannter Knoten — Erkennung und Normalisierung.

Die semantische Suche kann **Bedeutung** finden, aber keine **Namen nachschlagen**. Wer
„Operator nennen" sucht, bekommt *erkennen*, *korrigieren*, *berichten*: Im Vektor
dominiert das Wort „Operator", und alle 1.278 Operator-Knoten liegen dort dicht
beieinander — das gesuchte Verb geht darin unter. Gemessen am 30.08.2026 fanden nur 5 von
8 Nachschlage-Anfragen ihren Begriff überhaupt, und zwar unberechenbar: „Operator
vergleichen" traf, „Operator nennen" nicht.

Dieses Modul erkennt solche Anfragen, damit die Suche sie anders behandeln kann.

**Die Regel.** Eine Nachschlage-Anfrage unterscheidet sich von einer thematischen daran,
dass nach Abzug der Füllwörter ein *Name* übrig bleibt:

* „Was bedeutet der Operator nennen?" → ``nennen`` — ein Wort, ein Name.
* „Gedichte interpretieren und sprachliche Bilder deuten" → fünf Wörter, die zusammen
  keinen Knoten benennen.

Erkannt wird deshalb nur, wenn der Rest **genau ein Wort** ist oder als **ganze Wortfolge**
einem Titel entspricht. Die schwächere Regel „irgendein Wort der Anfrage trifft einen
Titel" wurde verworfen: Sie feuert bei „Gedichte **interpretieren** …" auf den gleichnamigen
Operator und verschlechtert genau den Fall, um den es geht.

Gemessen: 10 von 11 Nachschlage-Anfragen erkannt, **0 Fehlzündungen** bei den 15
thematischen Anfragen des Prüfsatzes.
"""

import re

# Führende Gliederungsnummer eines Bildungsplan-Titels: „3.6.1(13) Text", „(13) Text",
# „2.1 Text". Ohne sie ist ein Titel nicht nachschlagbar — niemand tippt die Nummer mit.
_GLIEDERUNGSNUMMER = re.compile(r"^\s*(?:\d+(?:\.\d+)*)?\s*(?:\(\d+\))?\s*")

_WORT = re.compile(r"[\wäöüßÄÖÜ\-]+")

# Wörter, die eine Nachschlage-Absicht ausdrücken, ohne selbst etwas zu benennen. Zwei
# Gruppen, und beide sind nötig:
#
# * **Fachliche Rahmenwörter** — „Operator", „Definition", „Bedeutung", „Leitidee" wäre
#   falsch (sie steht in Titeln!), aber „Operator" nicht: Kein Knoten heißt so, das Wort
#   beschreibt nur, *wonach* gesucht wird.
# * **Allgemeine Füllwörter** — Artikel, Präpositionen, Frage- und Aufforderungsverben.
#
# Bewusst **keine** YAML-Konfiguration: Die Liste ist eine Eigenschaft der deutschen
# Sprache und des Bildungsplan-Vokabulars, nicht der einzelnen Schule.
GENERISCHE_WOERTER: frozenset[str] = frozenset({
    # wonach gesucht wird, ohne es zu benennen
    "operator", "operators", "operatoren", "definition", "definitionen",
    "bedeutung", "bedeutungen", "bedeutet", "erklärung", "beschreibung",
    "übersicht", "überblick", "liste",
    "fach", "fächer", "fächern", "fachbereich", "fachbereiche", "fachbereichen",
    "kontextspeicher", "wissensgraph", "bildungsplan",
    # Aufforderung und Frage
    "erstelle", "erkläre", "erklär", "nenne", "zeige", "zeig", "gib", "suche",
    "nutze", "verwende", "brauche", "möchte", "will",
    "was", "wie", "welche", "welcher", "welches", "lautet", "bitte", "mir",
    # allgemeine Füllwörter
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einer",
    "eines", "einem", "und", "oder", "für", "von", "vom", "als", "auf", "aus",
    "bei", "mit", "nach", "über", "zu", "zur", "zum", "im", "in", "am", "an",
    "ist", "sind", "wird", "werden", "dazu", "damit", "dabei",
    "verschiedene", "verschiedenen", "einzelne", "einzelnen", "allen", "alle",
})


def ohne_gliederungsnummer(titel: str) -> str:
    """``"3.3.2 Leitidee Messen"`` → ``"Leitidee Messen"``.

    Auch von :mod:`app.context.embedding` genutzt — dieselbe Normalisierung muss beim
    Einbetten und beim Nachschlagen gelten, sonst findet man Titel, die anders eingebettet
    wurden (oder umgekehrt).
    """
    return _GLIEDERUNGSNUMMER.sub("", titel or "")


def normalisiere_titel(titel: str) -> str:
    """Titel in die Form bringen, in der verglichen wird: ohne Nummer, klein, einfache
    Leerzeichen."""
    return " ".join(ohne_gliederungsnummer(titel).lower().split())


def titel_normalisiert_sql(spalte: str) -> str:
    """Dieselbe Normalisierung wie :func:`normalisiere_titel`, als SQL-Ausdruck.

    **Eine Quelle für zwei Verwendungen:** die Nachschlage-Abfrage und den Index, der sie
    schnell macht (Migration 0053). Weichen beide voneinander ab, wird der Index
    **stillschweigend nicht benutzt** — die Suche liefert dann dasselbe Ergebnis, nur
    rund 70 ms langsamer je Anfrage. Ein Fehler, der nirgends auffällt: genau die Sorte,
    die dieses Projekt schon einmal ein halbes Jahr lang mitgeschleppt hat.

    Der Ausdruck ist ``IMMUTABLE`` und damit indizierbar.
    """
    return (
        f"lower(btrim(regexp_replace(regexp_replace({spalte}, "
        r"'^\s*(\d+(\.\d+)*)?\s*(\(\d+\))?\s*', ''), '\s+', ' ', 'g')))"
    )


# Grundwörter, die im Deutschen **Zusammensetzungen** bilden. Der Kopf steht hinten, also
# genügt der Blick aufs Wortende: „Operatorendefinitionen" ist so generisch wie
# „Definitionen", „Operatorenübersicht" so generisch wie „Übersicht".
#
# Bewusst knapp gehalten und auf eindeutige Meta-Wörter beschränkt. „Beschreibung" steht
# etwa **nicht** darin: „Bildbeschreibung" wäre ein legitimer Knotenname, und die Regel
# würde ihn stillschweigend wegwerfen.
_GENERISCHE_GRUNDWOERTER: tuple[str, ...] = (
    "definition", "definitionen", "bedeutung", "bedeutungen",
    "übersicht", "überblick",
)


def _ist_generisch(wort: str) -> bool:
    if wort in GENERISCHE_WOERTER:
        return True
    return any(
        wort.endswith(grund) and len(wort) > len(grund)
        for grund in _GENERISCHE_GRUNDWOERTER
    )


def reduziere(frage: str) -> list[str]:
    """Anfrage auf die Wörter reduzieren, die etwas benennen könnten.

    Kleinschreibung, Satzzeichen weg, generische Wörter weg — auch als Bestandteil einer
    Zusammensetzung (siehe ``_GENERISCHE_GRUNDWOERTER``). Wörter mit weniger als drei
    Zeichen fallen mit heraus; sie tragen keinen Namen und stammen fast immer aus der
    Frageform.
    """
    return [
        w for w in _WORT.findall((frage or "").lower())
        if not _ist_generisch(w) and len(w) > 2
    ]


def nachschlage_begriff(frage: str) -> str | None:
    """Der nachgeschlagene Begriff — oder ``None``, wenn es keine Nachschlage-Anfrage ist.

    Zurückgegeben wird die **normalisierte Form**, die gegen
    :func:`normalisiere_titel` verglichen werden kann. Ob es einen Knoten dieses Namens
    gibt, entscheidet die Datenbank; hier wird nur die *Absicht* erkannt.

    Zwei Formen gelten:

    * genau ein verbleibendes Wort (``"Operator nennen"`` → ``"nennen"``),
    * die vollständige verbleibende Wortfolge (``"Was ist die Leitidee Messen?"`` →
      ``"leitidee messen"``).

    Die zweite Form ist die engere: Sie trifft nur, wenn die Anfrage den Titel praktisch
    wörtlich enthält. Deshalb darf sie mehrere Wörter umfassen, ohne dass thematische
    Anfragen fälschlich als Nachschlagen gelten.
    """
    rest = reduziere(frage)
    if not rest:
        return None
    return rest[0] if len(rest) == 1 else " ".join(rest)
