"""Den Jahrgang einer Unterrichtsgruppe aus ihrem Namen ableiten.

⚠️ **Eine Vorbelegung, keine Wahrheit.** Der Jahrgang steht kanonisch in
`groups.jahrgang`; diese Regel füllt das Feld vor und springt ein, solange es leer ist.
Wo das Namensmuster nicht greift — freie Kursnamen, andere Schreibweisen, eine Schule mit
anderer Systematik —, muss ein Mensch es sagen können. Dasselbe Muster wie
`groups.erbt_mitglieder` (Alembic 0069): abgeleitet vorgeschlagen, entschieden gespeichert.

**Warum es die Regel überhaupt braucht.** `curriculum_resolver._group_grade` leitete den
Jahrgang **ausschließlich** über `group_source_classes` ab. Gruppen aus dem Stundenplan
und Kursstufenkurse haben dort nichts; gemessen am 24.09.2026 blieb für `ch-tl-abi28` und
`nwt-tl-10abcd` der Jahrgang `None` — und die Curriculum-Auflösung bot daraufhin **alle**
Curricula des Fachs an, einem Abi-28-Kurs also „CH Kl. 8".
"""

from __future__ import annotations

import re

# Die Kursstufe endet mit dem Abitur. Diese Zahl ist die eine Annahme dieser Datei:
# G8 in Baden-Württemberg, Abitur am Ende von Jahrgang 12. An einer G9-Schule liegt die
# Ableitung um eins daneben — **korrigierbar**, und genau dafür gibt es das Feld.
ABITURJAHRGANG = 12

# Was als Jahrgang überhaupt plausibel ist. Ohne diese Schranke würde aus „nwt-tl-2024"
# der Jahrgang 2024, und aus einem Tippfehler eine Zahl, die niemandem auffällt.
KLEINSTER, GROESSTER = 1, 13

_ABI = re.compile(r"\babi\s*[-_]?\s*(\d{2}|\d{4})\b", re.IGNORECASE)
_KLASSE = re.compile(r"(?<!\d)(\d{1,2})(?!\d)")


def _abiturjahr(roh: str) -> int:
    """„28" → 2028, „2028" → 2028."""
    zahl = int(roh)
    return zahl if zahl >= 1000 else 2000 + zahl


def leite_jahrgang_ab(name: str | None, *, schuljahr_ende: int) -> int | None:
    """Der Jahrgang, den der Name nahelegt — ``None``, wenn keiner erkennbar ist.

    `schuljahr_ende` ist das Kalenderjahr, in dem das laufende Schuljahr endet (aus
    `config/school_year.yaml`): Im Schuljahr 2026/27 also 2027.

    >>> leite_jahrgang_ab("nwt-tl-10abcd", schuljahr_ende=2027)
    10
    >>> leite_jahrgang_ab("9 Musik", schuljahr_ende=2027)
    9
    >>> leite_jahrgang_ab("ch-tl-abi28", schuljahr_ende=2027)
    11
    >>> leite_jahrgang_ab("Projektkurs", schuljahr_ende=2027) is None
    True
    """
    if not name:
        return None

    # ⚠️ **Abitur zuerst.** „ch-tl-abi28" enthält die Zahl 28; die Klassenregel machte
    # daraus einen 28. Jahrgang, und die Schranke unten verwürfe ihn stillschweigend —
    # aus einer ableitbaren Gruppe würde eine ohne Jahrgang.
    treffer = _ABI.search(name)
    if treffer:
        jahrgang = ABITURJAHRGANG - (_abiturjahr(treffer.group(1)) - schuljahr_ende)
        return jahrgang if KLEINSTER <= jahrgang <= GROESSTER else None

    for roh in _KLASSE.findall(name):
        jahrgang = int(roh)
        if KLEINSTER <= jahrgang <= GROESSTER:
            return jahrgang
    return None
