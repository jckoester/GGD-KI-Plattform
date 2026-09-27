"""Passt ein Baustein zur Klassenstufe der fragenden Person? (Paket 9, N6)

**Warum gekennzeichnet und sortiert wird, statt zu filtern.** „Oxidation" gibt es
zweimal: als Sauerstoffaufnahme (ab Klasse 8) und als Elektronenabgabe (ab Klasse 10).
Eine Neuntklässlerin bekam bis 09/2026 beide in beliebiger Reihenfolge, ohne Hinweis,
welche für sie gilt — die spätere Fassung stand sogar vorn.

⚠️ **Ausblenden wäre die schlechtere Lösung.** Fragt dieselbe Neuntklässlerin
ausdrücklich nach der Elektronen-Fassung, fände der Assistent nichts und antwortete aus
dem Modellwissen — also ohne die Definition ihrer Schule. Deshalb sieht er alles, mit
einem Vermerk je Treffer, und die passende Fassung steht vorn.

**Zwei Wege zur Stufe eines Bausteins, in dieser Reihenfolge:**

1. `metadata.ab_klasse` — nur bei Begriffen, die es in mehreren Fassungen gibt. Welche
   davon die aktuelle ist, entscheidet sich **im Vergleich der Fassungen
   untereinander**, nicht am einzelnen Knoten: Die höchste Stufe, die die Person schon
   erreicht hat, ist ihre; frühere sind Vorwissen.
2. Die Bildungsplan-Fundstellen des Knotens. Ihre Bänder stehen in den Daten
   (`min_grade`/`max_grade` an der Kompetenz) — sie müssen nicht nachgebaut werden.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.editions import aktive_bp_version
from app.db.models import ContextEdge, ContextNode

#: Knotenarten, für die ein Stufenvermerk überhaupt Sinn ergibt. Eine
#: Bildungsplan-Kompetenz trägt ihre Stufe im Titel, ein Arbeitsblatt hat keine.
VERMERKTE_TYPEN = ("begriff", "stoffsteckbrief")

#: Was an einem Treffer steht, der nicht zur Stufe passt.
VORWISSEN = "Vorwissen (frühere Fassung)"
FRUEHER = "früherer Stoff"


async def bp_baender_zu(
    db: AsyncSession, treffer: list[dict], stufe: int
) -> dict[str, tuple[int, int]]:
    """Das Klassenband je Knoten, aus seinen Bildungsplan-Fundstellen.

    Nur **aktive** Ziele, und nur in der Edition, die für diese Stufe und dieses Fach
    gilt (`aktive_bp_version`). Sonst zählte im Übergangsjahr die alte Fassung mit, und
    ein Begriff bekäme ein Band, das für die Person gar nicht gilt.
    """
    interessant = {
        str(t["node_id"]): t.get("subject_id")
        for t in treffer
        if t.get("content_type") in VERMERKTE_TYPEN and t.get("node_id")
    }
    if not interessant:
        return {}

    # Je Fach die geltende Edition — eine Abfrage für alle Fächer der Trefferliste.
    faecher = {f for f in interessant.values() if f is not None}
    if not faecher:
        return {}
    vorhanden: dict[int, set[str]] = {}
    for fach, version in (await db.execute(
        sa.select(ContextNode.subject_id, ContextNode.bp_version)
        .where(ContextNode.subject_id.in_(faecher), ContextNode.bp_version != "")
        .distinct()
    )).all():
        vorhanden.setdefault(fach, set()).add(version)
    geltend = {
        fach: aktive_bp_version(stufe, versionen) for fach, versionen in vorhanden.items()
    }
    if not any(geltend.values()):
        return {}

    ziel = sa.orm.aliased(ContextNode)
    zeilen = (await db.execute(
        sa.select(
            ContextEdge.from_node_id,
            sa.func.min(ziel.min_grade),
            sa.func.max(ziel.max_grade),
        )
        .join(ziel, ziel.id == ContextEdge.to_node_id)
        .where(
            ContextEdge.from_node_id.in_(list(interessant)),
            ContextEdge.relation == "references",
            ziel.status == "active",
            ziel.min_grade.isnot(None),
            sa.or_(*[
                sa.and_(ziel.subject_id == fach, ziel.bp_version == version)
                for fach, version in geltend.items() if version
            ]),
        )
        .group_by(ContextEdge.from_node_id)
    )).all()
    return {str(von): (lo, hi) for von, lo, hi in zeilen if lo is not None}


def _ab_klasse(treffer: dict) -> int | None:
    wert = (treffer.get("metadata") or {}).get("ab_klasse")
    return wert if isinstance(wert, int) and not isinstance(wert, bool) else None


def vermerke(
    treffer: list[dict], stufe: int | None, baender: dict[str, tuple[int, int]]
) -> dict[str, str]:
    """Je Knoten ein Satz zur Stufe — oder gar nichts, wenn er passt.

    ⚠️ **Kein Vermerk ist die häufigste und richtige Antwort.** Ein Hinweis an jedem
    Treffer wäre Rauschen; er soll auffallen, wo etwas nicht zusammenpasst.
    """
    if stufe is None:
        return {}

    # Fassungen eines Begriffs erkennt man am gemeinsamen Titel. Welche die aktuelle
    # ist, ergibt sich erst im Vergleich: die höchste Stufe, die die Person erreicht hat.
    hoechste_erreichte: dict[str, int] = {}
    for t in treffer:
        ab = _ab_klasse(t)
        if ab is not None and ab <= stufe:
            titel = (t.get("title") or "").strip()
            hoechste_erreichte[titel] = max(hoechste_erreichte.get(titel, 0), ab)

    ergebnis: dict[str, str] = {}
    for t in treffer:
        if t.get("content_type") not in VERMERKTE_TYPEN or not t.get("node_id"):
            continue
        knoten_id, titel = str(t["node_id"]), (t.get("title") or "").strip()
        ab = _ab_klasse(t)
        if ab is not None:
            if ab > stufe:
                ergebnis[knoten_id] = f"kommt ab Klasse {ab}"
            elif ab < hoechste_erreichte.get(titel, ab):
                ergebnis[knoten_id] = VORWISSEN
            continue
        band = baender.get(knoten_id)
        if band is None:
            continue                      # keine Fundstelle → keine Aussage
        unten, oben = band
        if stufe < unten:
            ergebnis[knoten_id] = f"kommt ab Klasse {unten}"
        elif oben is not None and stufe > oben:
            ergebnis[knoten_id] = FRUEHER
    return ergebnis


def sortiere_passende_nach_vorn(treffer: list[dict], vermerke_: dict[str, str]) -> list[dict]:
    """Passendes zuerst — **stabil**, damit die Ähnlichkeit innerhalb der Gruppen bleibt.

    Zwei Gruppen, nicht drei: „kommt später" und „Vorwissen" gegeneinander zu ordnen
    hieße, eine Vorliebe zu behaupten, für die es keine Grundlage gibt. Die Reihenfolge
    innerhalb einer Gruppe stammt weiter aus der Suche.
    """
    return sorted(treffer, key=lambda t: 1 if vermerke_.get(str(t.get("node_id"))) else 0)
