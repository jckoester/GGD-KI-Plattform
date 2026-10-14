"""Begriffsnennung im Satz — die erste Quelle des Vorab-Angebots (0.16).

Schreibt eine Schüler:in „Letzte Stunde haben wir etwas über Elektronegativität gelernt, das
ich nicht ganz verstanden habe", nennt sie den Begriff beim Namen — aber in einem Satz. Der
exakte Namenstreffer (Weg 1) sieht nur die ganze Nachricht, die Distanz (Weg 2) verwässert im
Erzählrahmen. Gemessen (Prüfsatz `vorab_begriffe.py`, 14.10.2026): 138 von 240 Erzählsätzen
fanden ihren Begriff; eine höhere Schwelle brachte schon bei 0,46 neue Fehltreffer.

**Was hier geschieht:** Titel und Aliase der Vorab-Typen werden als Wortfolgen in der
Nachricht gesucht — an Wortgrenzen, längste zuerst, mit einfachen Endungen auf **beiden**
Seiten („eines Alkans" trifft den Titel „Alkane"). Keine Komposita: „Veresterungsreaktion"
nennt die Veresterung nicht.

⚠️ **Eine Nennung allein genügt nicht.** Ohne weitere Prüfung brächte „Wir wollen nachher ein
Eis essen" den Steckbrief Wasser (Alias „Eis") in den Prompt, „Wie hoch ist der Eiffelturm?"
die Potenz (Alias „hoch"). Wortlisten oder eine Mindestlänge hälfen nicht („Untersuchung",
„Mechanismus", „Resonanz"). Auch ein Tor auf der Distanz trennt sie nicht: „Stoff", „Probe"
und „Reduktion" im Alltagssinn liegen so nah wie gewollte Nennungen (Reihe 2, 14.10.2026).
Deshalb liefert dieses Modul nur **Kandidaten**, und eine Nennung führt in `search.vorab()`
nur zum **Angebot** — der Titel steht im Systemtext, den Inhalt holt das Modell, wenn er für
die Antwort zählt. Ein liegengelassener Titel verbiegt die Antwort nicht; ein Inhalt würde
geglaubt (Plan „Vorab-Suche-Begriffe", § 7).

**Fachbezug:** In einem Chat mit Fach zählen nur Begriffe dieses Fachs, seiner Bezugsfächer
(`subjects.bezugsfaecher`) und fachlose. Ein Begriff außerhalb kommt über die Nennung nicht
herein — über die Distanz wie bisher schon (F8, gemessen gegen Ende von 0.16).

**Kein Datenbankaufruf je Nachricht:** Die Namen liegen in einem Index im Speicher, der nach
:data:`INDEX_TTL` Sekunden neu gelesen wird. Ein neuer Begriff wird also spätestens nach einer
Minute im Satz erkannt; einen Vektor braucht er ohnehin, und der entsteht auch nicht sofort.
Sichtbarkeit und Status prüft die Abfrage in `vorab()` — der Index kennt nur Namen.
"""
import asyncio
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.lookup import normalisiere_titel
from app.context.taxonomy import VORAB_TYPEN
from app.db.models import ContextNode, NodeAlias

#: Einfache Endungen (Plural, Genitiv), längste zuerst. Abgeschnitten wird höchstens eine,
#: und nur, wenn mindestens drei Zeichen bleiben — „Ion" bleibt „ion", „Ionen" wird es.
ENDUNGEN = ("en", "es", "e", "n", "s")

#: Längere Namen werden nicht im Satz gesucht. Kein Begriff heißt so lang; Methodenblätter
#: tragen Titel wie „Merkblatt zur Gedichtanalyse in der Mittelstufe" (6 Wörter).
MAX_WOERTER = 8

#: Wie lange der Namensindex gilt (Sekunden).
INDEX_TTL = 60.0

_WORT = re.compile(r"\w+(?:-\w+)*")


def stamm(wort: str) -> str:
    """Ein Wort ohne einfache Endung: „alkane" → „alkan", „ionen" → „ion", „mittelwerts" →
    „mittelwert". Beide Seiten — Name und Nachricht — gehen hier durch, deshalb treffen sich
    Singular und Plural in beiden Richtungen."""
    for endung in ENDUNGEN:
        if wort.endswith(endung) and len(wort) - len(endung) >= 3:
            return wort[: -len(endung)]
    return wort


def schluessel(text: str) -> tuple[str, ...]:
    """Die Wortstämme eines Namens oder einer Nachricht, normalisiert wie Titel."""
    return tuple(stamm(w) for w in _WORT.findall(normalisiere_titel(text)))


@dataclass(frozen=True)
class Eintrag:
    node_id: str
    subject_id: int | None
    ist_titel: bool


@dataclass
class Namensindex:
    """Wortstämme eines Namens → die Knoten, die so heißen (als Titel oder Alias)."""

    namen: dict[tuple[str, ...], list[Eintrag]] = field(default_factory=dict)
    laengste: int = 0

    @classmethod
    def aus(cls, titel: Iterable[tuple], aliase: Iterable[tuple]) -> "Namensindex":
        """``titel``: (node_id, subject_id, Titel); ``aliase``: (node_id, subject_id, Alias)."""
        index = cls()
        for quelle, ist_titel in ((titel, True), (aliase, False)):
            for node_id, subject_id, name in quelle:
                k = schluessel(name or "")
                if not k or len(k) > MAX_WOERTER:
                    continue
                index.namen.setdefault(k, []).append(Eintrag(str(node_id), subject_id, ist_titel))
                index.laengste = max(index.laengste, len(k))
        return index


def genannt(text: str, index: Namensindex, erlaubt: set[int] | None) -> dict[str, str]:
    """Die in ``text`` genannten Knoten: ``node_id`` → ``"titel"`` oder ``"alias"``.

    **Längste zuerst:** Ist „systematische Messfehler" als Ganzes genannt, zählt das Wort
    „Messfehler" darin nicht noch einmal für sich. **Titel vor Alias:** Nennt die Nachricht
    einen Knoten über beides, gilt das weitere Tor des Titels.

    ``erlaubt``: die Fächer, aus denen eine Nennung kommen darf (Chat-Fach und Bezugsfächer);
    ``None`` im Chat ohne Fach. Fachlose Knoten sind immer erlaubt. Ein Name aus einem Fach
    außerhalb zählt **gar nicht** — er belegt auch keine Wörter, die ein kürzerer Name aus
    dem eigenen Fach bräuchte.
    """
    woerter = schluessel(text)
    belegt = [False] * len(woerter)
    ergebnis: dict[str, str] = {}
    for laenge in range(min(index.laengste, len(woerter)), 0, -1):
        for start in range(len(woerter) - laenge + 1):
            if any(belegt[start:start + laenge]):
                continue
            eintraege = [
                e for e in index.namen.get(woerter[start:start + laenge], ())
                if erlaubt is None or e.subject_id is None or e.subject_id in erlaubt
            ]
            if not eintraege:
                continue
            for i in range(start, start + laenge):
                belegt[i] = True
            for e in eintraege:
                if e.ist_titel:
                    ergebnis[e.node_id] = "titel"
                else:
                    ergebnis.setdefault(e.node_id, "alias")
    return ergebnis


# ── Index im Speicher ────────────────────────────────────────────────────────

_index: tuple[Namensindex, float] | None = None


def verwerfen() -> None:
    """Den Index beim nächsten Aufruf neu lesen (Tests, nach einem Import)."""
    global _index
    _index = None


async def namensindex(db: AsyncSession) -> Namensindex:
    """Titel und Aliase aller aktiven Vorab-Knoten — höchstens :data:`INDEX_TTL` alt."""
    global _index
    jetzt = asyncio.get_event_loop().time()
    if _index is not None and jetzt < _index[1]:
        return _index[0]
    aktiv = (ContextNode.status == "active", ContextNode.content_type.in_(VORAB_TYPEN))
    titel = (await db.execute(
        sa.select(ContextNode.id, ContextNode.subject_id, ContextNode.title).where(*aktiv)
    )).all()
    aliase = (await db.execute(
        sa.select(NodeAlias.node_id, ContextNode.subject_id, NodeAlias.alias)
        .join(ContextNode, ContextNode.id == NodeAlias.node_id)
        .where(*aktiv)
    )).all()
    index = Namensindex.aus(titel, aliase)
    _index = (index, jetzt + INDEX_TTL)
    return index
