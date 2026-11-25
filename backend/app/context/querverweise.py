"""Querverweise des Bildungsplans in ein anderes Fach (Päckchen AY Teil 1, Schritt 2).

Der Bildungsplan nennt an vielen Kompetenzen, wo ein **anderes Fach** anschließt
(„siehe auch PH 3.4.3 Schwingungen“). Der Import legt diese Verweise als Kanten
``related_to`` an (``scripts/import_bildungsplan.py``). Diese Funktion liest sie für eine
Menge von Kompetenzen, etwa die eines Curriculums.

Entschieden (Jan, 25.11.2026, Plan ``Querverweise-im-Curriculum-AY1-Plan``):

- **Beide Richtungen** (F2): Der Plan meint „siehe auch“, die Kanten stehen aber fast nur
  einseitig (Dev: 30 von etwa 3.000 gegenseitig).
- **Bereiche bleiben Bereiche** (F3 a): Gut die Hälfte der Verweise zielt im Bildungsplan
  selbst auf einen Bereich (``leitidee``), nicht auf eine Kompetenz. Aufgefächert wird nicht.
- **Fassung** (F4): Ein archiviertes Ziel (knapp ein Drittel, alte Fassung, ohne
  ``supersedes``) wird über (Fach, Typ, Nummer, Stufenband) auf die aktive Fassung umgelenkt,
  sonst auf eine künftige; ohne Treffer fällt es weg. Das Band gehört zum Schlüssel, weil
  Nummern sich zwischen den Bändern wiederholen („3.2.1(3)“ steht in V2 für 7/8 und in V3
  für 9/10). Ein künftiges Ziel bleibt und trägt ``ab_schuljahr``.

Leserecht: Ziele sind nur Bildungsplan-Knoten (die drei Typen unten), und die liest jede
angemeldete Person. Eine Prüfung je Nutzer:in braucht es deshalb hier nicht — das Curriculum,
aus dem die Kompetenzen stammen, prüft der Aufrufer.
"""
from __future__ import annotations

import re
from collections import defaultdict
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.editions import KUENFTIG, gilt_ab_schuljahr
from app.db.models import ContextEdge, ContextNode, Subject

#: Bildungsplan-Typen, die als Ziel zählen, mit dem Namen für die Oberfläche.
ZIELTYPEN = {"ik_kompetenz": "ik", "leitidee": "bereich", "pk_kompetenz": "pk"}

_SICHTBAR = ("active", KUENFTIG)
# Stufenband aus der Kennung: …_PH.V2_IK_11-12-BF-QUANTEN_03_00_01 → „11-12-BF-QUANTEN“.
_BAND = re.compile(r"_(?:IK|PK)_([^_]+)_")
_STUFEN = re.compile(r"^(\d+)(?:-(\d+))*")
# Führende Nummer im Titel: „3.2.3 Energie“, „3.2.1(3) die Funktion …“, „2.2.35 …“.
_NR_IM_TITEL = re.compile(r"^\s*\d+(?:\.\d+)*(?:\s*\(\d+\))?\s+")


def nummer(knoten: ContextNode) -> str | None:
    meta = knoten.metadata_ or {}
    return meta.get("kompetenz_nr") or meta.get("nr")


def band(knoten: ContextNode) -> str | None:
    treffer = _BAND.search((knoten.metadata_ or {}).get("bp_id") or "")
    return treffer.group(1) if treffer else None


def stufen(knoten: ContextNode) -> tuple[int | None, int | None]:
    """Aus den Spalten, sonst aus dem Band (Oberstufen-Knoten tragen oft keine Stufen)."""
    if knoten.min_grade is not None or knoten.max_grade is not None:
        return knoten.min_grade, knoten.max_grade
    treffer = _STUFEN.match(band(knoten) or "")
    if not treffer:
        return None, None
    zahlen = [int(z) for z in re.findall(r"\d+", treffer.group(0))]
    return min(zahlen), max(zahlen)


def kurztitel(titel: str) -> str:
    return _NR_IM_TITEL.sub("", titel or "", count=1).strip()


def _schluessel(knoten: ContextNode) -> tuple:
    return knoten.subject_id, knoten.content_type, nummer(knoten), band(knoten)


async def _umlenken(db: AsyncSession, alte: list[ContextNode]) -> dict[UUID, ContextNode]:
    """Archivierte Ziele → aktive (sonst künftige) Fassung mit gleichem Schlüssel."""
    gesucht = {_schluessel(k) for k in alte if nummer(k)}
    if not gesucht:
        return {}
    nr_ausdruck = sa.func.coalesce(ContextNode.metadata_["kompetenz_nr"].astext,
                                   ContextNode.metadata_["nr"].astext)
    kandidaten = (await db.execute(sa.select(ContextNode).where(
        ContextNode.subject_id.in_({s for s, *_ in gesucht}),
        ContextNode.content_type.in_({t for _, t, *_ in gesucht}),
        ContextNode.status.in_(_SICHTBAR),
        nr_ausdruck.in_({n for _, _, n, _ in gesucht}),
    ))).scalars().all()
    bester: dict[tuple, ContextNode] = {}
    for k in kandidaten:
        s = _schluessel(k)
        if s in gesucht and (s not in bester or (bester[s].status != "active" and k.status == "active")):
            bester[s] = k
    return {k.id: bester[_schluessel(k)] for k in alte if _schluessel(k) in bester}


async def querverweise(db: AsyncSession, kompetenz_ids: list[UUID]) -> dict[str, list[dict]]:
    """Je Kompetenz (ID als Text) die Querverweise in andere Fächer, sortiert nach Fach und
    Nummer. Kompetenzen ohne Querverweis fehlen in der Rückgabe."""
    ids = set(kompetenz_ids)
    if not ids:
        return {}
    kanten = (await db.execute(sa.select(ContextEdge.from_node_id, ContextEdge.to_node_id).where(
        ContextEdge.relation == "related_to",
        sa.or_(ContextEdge.from_node_id.in_(ids), ContextEdge.to_node_id.in_(ids)),
    ))).all()
    paare = [(von, zu) for von, zu in kanten if von in ids] + [(zu, von) for von, zu in kanten if zu in ids]
    if not paare:
        return {}

    knoten = {k.id: k for k in (await db.execute(sa.select(ContextNode).where(
        ContextNode.id.in_({q for q, _ in paare} | {z for _, z in paare})))).scalars()}
    archiviert = [k for k in knoten.values()
                  if k.content_type in ZIELTYPEN and k.status not in _SICHTBAR]
    umgelenkt = await _umlenken(db, archiviert)

    ziele: dict[UUID, dict[UUID, ContextNode]] = defaultdict(dict)
    for quelle_id, ziel_id in paare:
        quelle, ziel = knoten.get(quelle_id), knoten.get(ziel_id)
        if quelle is None or ziel is None or ziel.content_type not in ZIELTYPEN:
            continue
        if ziel.status not in _SICHTBAR:
            ziel = umgelenkt.get(ziel.id)
            if ziel is None:
                continue
        if ziel.subject_id is None or ziel.subject_id == quelle.subject_id:
            continue
        ziele[quelle_id][ziel.id] = ziel

    faecher = {f.id: f for f in (await db.execute(sa.select(Subject).where(
        Subject.id.in_({z.subject_id for je in ziele.values() for z in je.values()})))).scalars()}

    aus: dict[str, list[dict]] = {}
    for quelle_id, je in ziele.items():
        liste = []
        for z in je.values():
            fach = faecher[z.subject_id]
            min_g, max_g = stufen(z)
            liste.append({
                "ziel_id": str(z.id), "typ": ZIELTYPEN[z.content_type],
                "fach_id": fach.id, "fach": fach.name, "fach_code": fach.fach_code,
                "fach_slug": fach.slug, "icon": fach.icon, "color": fach.color,
                "nr": nummer(z), "titel": kurztitel(z.title),
                "min_grade": min_g, "max_grade": max_g, "status": z.status,
                "ab_schuljahr": (gilt_ab_schuljahr(z.bp_version, min_g, max_g)
                                 if z.status == KUENFTIG else None),
                "_sort": (fach.sort_order, fach.name, min_g or 0, _nr_sortierbar(nummer(z))),
            })
        liste.sort(key=lambda e: e["_sort"])
        for e in liste:
            del e["_sort"]
        aus[str(quelle_id)] = liste
    return aus


def _nr_sortierbar(nr: str | None) -> tuple:
    return tuple(int(z) for z in re.findall(r"\d+", nr or ""))
