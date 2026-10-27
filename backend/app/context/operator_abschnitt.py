"""Abschnitt „Operator dieser Aufgabe" — Päckchen AF (0.23), Schritt 3.

Nennt eine Schülernachricht einen Operator („Erläutere …", :mod:`app.context.operator_erkennung`),
holt dieses Modul dessen Definition **in der Fassung der Klasse** und baut daraus den
Abschnitt, den der Prompt mit Prüfregel (v5d) erwartet. Gemessen wurde er im Prüfregel-Versuch
als Zusatz von Hand (Läufe 14–18, Arm B); hier entsteht derselbe Text aus dem Wissensspeicher.

**Fächerkreis** (Plan F2/F4): die Fächer des Assistenten (`assistants.operator_faecher`), davon
nur die, die in der Klassenstufe unterrichtet werden (`subjects.min_grade/max_grade` — Chemie
gibt es in Klasse 7 nicht). Liegt das Fach der Konversation im Kreis, gilt nur dieses.

**Gleicher Wortlaut wird zusammengefasst** (Plan B5): In einer Fassung sind die NW-Fächer
meist wortgleich. Unterscheidet sich der Wortlaut, stehen alle Fassungen mit ihren Fächern da.

**Abgrenzung** (Plan B7): Zu *bewerten* gehört *beurteilen* und umgekehrt — aber nur, wenn
der Partner in derselben Fassung vorkommt (in V3; in V2 fasst *bewerten* beides). Die
Operator-Knoten tragen keine Abgrenzungs-Kanten, deshalb steht das Paar hier im Code.
"""
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.filters import Knotenfilter
from app.context.operator_erkennung import Operatorindex, erkenne
from app.context.search import Suchprofil, aufzaehlung
from app.db.models import ContextNode, Subject

#: Überschrift des Abschnitts — so steht sie im Prompt (v5d, „Operator dieser Aufgabe").
UEBERSCHRIFT = "## Operator dieser Aufgabe"

#: Operatoren, deren Unterschied die Definition trägt (Prüfregel-Versuch O3/O5).
ABGRENZUNG = {"bewerten": "beurteilen", "beurteilen": "bewerten"}

#: Wie lange der Operatorindex eines Fächerkreises gilt (Sekunden) — wie `nennung.INDEX_TTL`.
INDEX_TTL = 60.0

_indizes: dict[tuple[int, ...], tuple[Operatorindex, float]] = {}


@dataclass
class Operatorabschnitt:
    """Was :func:`operator_abschnitt` liefert: der Text und, für den Messkanal, woraus er besteht."""

    text: str
    operatoren: list[str]
    faecher: list[str] = field(default_factory=list)
    fassungen: list[str] = field(default_factory=list)


async def _kreis(
    db: AsyncSession, slugs: Sequence[str], konversationsfach_id: int | None, stufe: int | None
) -> list[int]:
    zeilen = (await db.execute(
        sa.select(Subject.id, Subject.min_grade, Subject.max_grade).where(Subject.slug.in_(list(slugs)))
    )).all()
    kreis = [
        i for i, von, bis in zeilen
        if stufe is None or ((von is None or von <= stufe) and (bis is None or stufe <= bis))
    ]
    if konversationsfach_id is not None and konversationsfach_id in kreis:
        return [konversationsfach_id]
    return sorted(kreis)


async def _index(db: AsyncSession, kreis: list[int]) -> Operatorindex:
    """Operator-Titel des Kreises als Index — im Speicher, je Kreis, mit :data:`INDEX_TTL`."""
    schluessel = tuple(kreis)
    vorhanden = _indizes.get(schluessel)
    if vorhanden and time.monotonic() - vorhanden[1] < INDEX_TTL:
        return vorhanden[0]
    titel = (await db.execute(
        sa.select(ContextNode.title).distinct().where(
            ContextNode.content_type == "operator",
            ContextNode.status == "active",
            ContextNode.subject_id.in_(kreis),
        )
    )).scalars().all()
    index = Operatorindex.aus(titel)
    _indizes[schluessel] = (index, time.monotonic())
    return index


def _fassung(stufe: int | None, bp_versionen: Sequence[str | None]) -> str:
    """„Fassung für Klasse 9" — ohne Stufe die Kürzel der Fassungen („Fassung V2, 2016")."""
    if stufe is not None:
        return f"Fassung für Klasse {stufe}"
    kurz = sorted({(v or "").split(".")[-1] for v in bp_versionen} - {""})
    return f"Fassung {', '.join(kurz)}" if kurz else "Fassung"


async def _definitionen(
    db: AsyncSession, titel: str, kreis: list[int], stufe: int | None, pseudonym: str,
    rollen: Sequence[str],
) -> list[dict]:
    """Die Treffer eines Operators im Kreis — mit Stufe in der geltenden Fassung je Fach,
    ohne Stufe die neueste je Fach (wie bis 0.22 `get_operatoren`)."""
    abschnitt = await aufzaehlung(
        Knotenfilter(titel=titel, content_type=("operator",), subject_ids=tuple(kreis)),
        Suchprofil(pseudonym=pseudonym, rollen=tuple(rollen), grade=stufe, aufzaehlung=50),
        db,
    )
    neueste: dict[int | None, dict] = {}
    for t in abschnitt.treffer:
        bisher = neueste.get(t.get("subject_id"))
        if bisher is None or (t.get("bp_version") or "") > (bisher.get("bp_version") or ""):
            neueste[t.get("subject_id")] = t
    return [t for t in neueste.values() if (t.get("content") or "").strip()]


def _zeilen(titel: str, treffer: list[dict], stufe: int | None, praefix: str = "") -> list[str]:
    """Je Wortlaut eine Zeile: „erläutern (Biologie, Physik, Fassung für Klasse 7): …"."""
    nach_wortlaut: dict[str, list[dict]] = {}
    for t in treffer:
        nach_wortlaut.setdefault(" ".join(t["content"].split()), []).append(t)
    zeilen = []
    for wortlaut, gruppe in nach_wortlaut.items():
        faecher = ", ".join(sorted({t.get("fach") or "?" for t in gruppe}))
        fassung = _fassung(stufe, [t.get("bp_version") for t in gruppe])
        zeilen.append(f"{praefix}{titel} ({faecher}, {fassung}): {wortlaut}")
    return zeilen


async def operator_abschnitt(
    nachrichten: Sequence[str],
    faecher_slugs: Sequence[str],
    *,
    konversationsfach_id: int | None,
    stufe: int | None,
    pseudonym: str,
    rollen: Sequence[str],
    db: AsyncSession,
) -> Operatorabschnitt | None:
    """Der Abschnitt zur jüngsten Nachricht, die einen Operator nennt.

    ``nachrichten``: Texte der Nutzer:in, **neueste zuerst** — ein Folgezug („keine ahnung")
    nennt den Operator nicht mehr, die Aufgabe davor schon (Plan B6). ``None``, wenn der
    Assistent keinen Kreis führt, keine Nachricht einen Operator nennt oder keine
    Definition gefunden wird.
    """
    if not faecher_slugs:
        return None
    kreis = await _kreis(db, faecher_slugs, konversationsfach_id, stufe)
    if not kreis:
        return None
    index = await _index(db, kreis)
    erkannt: list[str] = []
    for text in nachrichten:
        erkannt = erkenne(text or "", index)
        if erkannt:
            break
    if not erkannt:
        return None

    zeilen: list[str] = []
    faecher: set[str] = set()
    fassungen: set[str] = set()
    for titel in erkannt:
        treffer = await _definitionen(db, titel, kreis, stufe, pseudonym, rollen)
        if not treffer:
            continue
        zeilen += _zeilen(titel, treffer, stufe)
        partner = ABGRENZUNG.get(titel)
        if partner and partner not in erkannt:
            # Nur, wo der Partner in **derselben** Fassung steht wie der Operator selbst.
            eigene = {(t.get("subject_id"), t.get("bp_version")) for t in treffer}
            gegen = [t for t in await _definitionen(db, partner, kreis, stufe, pseudonym, rollen)
                     if (t.get("subject_id"), t.get("bp_version")) in eigene]
            if gegen:
                zeilen += _zeilen(partner, gegen, stufe, praefix="Abgrenzung – ")
        faecher |= {t.get("fach") or "?" for t in treffer}
        fassungen |= {t.get("bp_version") or "" for t in treffer}
    if not zeilen:
        return None
    return Operatorabschnitt(
        text="\n".join([UEBERSCHRIFT, *zeilen]),
        operatoren=erkannt,
        faecher=sorted(faecher),
        fassungen=sorted(f for f in fassungen if f),
    )
