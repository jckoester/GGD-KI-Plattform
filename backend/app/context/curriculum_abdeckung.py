"""Abdeckung eines Curriculums (0.45, Päckchen AP Teil A, Punkt 6).

Je inhaltsbezogener Kompetenz (IK) des Bands: verknüpft, nur partiell verknüpft oder nicht
verknüpft; dazu je prozessbezogener Kompetenz (PK), wie viele Lernsequenzen sie fördern.
Für die Anzeige im Curriculum und — in Teil B — für den Assistenten (`get_curriculum_coverage`):
Er rechnet nicht selbst, er liest diese Zahlen.

**Welche IK zum Band gehören.** Fach und Bildungsplan-Fassung des Curriculums, Stufen, die sich
mit denen des Curriculums überschneiden. Ein Curriculum für Klasse 9 sieht also die IK des
Bands 9/10. Weil Schulen ein Band oft auf zwei Curricula aufteilen, steht bei jeder
Kompetenz, welche **anderen** veröffentlichten Curricula desselben Bands sie verknüpfen
(`anderswo`) — am Zustand ändert das nichts.

**Was zählt.** Die Kanten der Lernsequenzen: `references` auf IK (mit `partiell` an der Kante)
und `develops` auf PK, wie sie der Editor schreibt. Verknüpfte IK, die nicht zum Band oder zur
Fassung gehören, stehen gesondert (`ausserhalb`) — etwa nach einem Fassungswechsel.
"""
from __future__ import annotations

import re
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models import ContextEdge, ContextNode

VERKNUEPFT, PARTIELL, FEHLT = "verknuepft", "partiell", "fehlt"
_NR_PRAEFIX = re.compile(r"^\s*\d+(?:\.\d+)*\s*(?:\(\d+\))?\s*")


def _sortschluessel(nr: str | None) -> list:
    """3.1.1(2) vor 3.1.1(11) — Zahlblöcke als Zahlen."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", nr or "")]


def _text(titel: str | None, nr: str | None) -> str:
    """Der Wortlaut ohne die vorangestellte Nummer."""
    titel = titel or ""
    return _NR_PRAEFIX.sub("", titel, count=1) if nr and titel.startswith(nr.split("(")[0]) else titel


def _lernsequenzen(tree: dict) -> dict[str, str]:
    return {str(ls["id"]): ls.get("title") or "" for kap in tree.get("kapitel", [])
            for ls in kap.get("lernsequenzen", [])}


def _bp_version(cur: ContextNode) -> str | None:
    return (cur.metadata_ or {}).get("bp_version") or cur.bp_version


async def abdeckung(db: AsyncSession, tree: dict) -> dict:
    """Die Abdeckung für einen Baum aus `load_curriculum_tree` (Rechte prüft der Aufrufer)."""
    cur = await db.get(ContextNode, tree["id"])
    bp = _bp_version(cur)
    ls_titel = _lernsequenzen(tree)
    ls_ids = [UUID(i) for i in ls_titel]
    leer = {"bp_version": bp, "min_grade": cur.min_grade, "max_grade": cur.max_grade,
            "ik": {"gesamt": 0, VERKNUEPFT: 0, PARTIELL: 0, FEHLT: 0, "fehlt_anderswo": 0, "gruppen": []},
            "pk": {"gesamt": 0, "genutzt": 0, "gruppen": []}, "ausserhalb": [], "hinweis": None}
    if cur.subject_id is None or not bp:
        return {**leer, "hinweis": "Fach oder Bildungsplan-Fassung des Curriculums fehlen."}

    im_fach = sa.and_(ContextNode.subject_id == cur.subject_id, ContextNode.bp_version == bp,
                      ContextNode.status != "deleted")
    band = sa.true()
    if cur.min_grade is not None and cur.max_grade is not None:
        band = sa.and_(sa.or_(ContextNode.min_grade.is_(None), ContextNode.min_grade <= cur.max_grade),
                       sa.or_(ContextNode.max_grade.is_(None), ContextNode.max_grade >= cur.min_grade))
    iks = (await db.execute(sa.select(ContextNode).where(
        ContextNode.content_type == "ik_kompetenz", im_fach, band))).scalars().all()
    pks = (await db.execute(sa.select(ContextNode).where(
        ContextNode.content_type == "pk_kompetenz", im_fach))).scalars().all()

    # Kanten dieses Curriculums: je Kompetenz die Lernsequenzen, bei IK mit `partiell`.
    kanten = (await db.execute(sa.select(
        ContextEdge.from_node_id, ContextEdge.to_node_id, ContextEdge.relation,
        ContextEdge.metadata_["partiell"].as_string(),
    ).where(ContextEdge.from_node_id.in_(ls_ids),
            ContextEdge.relation.in_(("references", "develops"))))).all() if ls_ids else []
    voll: dict[UUID, set[str]] = {}
    teil: dict[UUID, set[str]] = {}
    gefoerdert: dict[UUID, set[str]] = {}
    for ls_id, ziel, relation, partiell in kanten:
        if relation == "develops":
            gefoerdert.setdefault(ziel, set()).add(str(ls_id))
        else:
            (teil if partiell == "true" else voll).setdefault(ziel, set()).add(str(ls_id))

    anderswo = await _anderswo(db, cur, bp, [k.id for k in iks])

    gruppen: dict[str, list[dict]] = {}
    zaehler = {VERKNUEPFT: 0, PARTIELL: 0, FEHLT: 0, "fehlt_anderswo": 0}
    for k in sorted(iks, key=lambda k: _sortschluessel((k.metadata_ or {}).get("kompetenz_nr"))):
        meta = k.metadata_ or {}
        nr = meta.get("kompetenz_nr")
        zustand = VERKNUEPFT if k.id in voll else PARTIELL if k.id in teil else FEHLT
        zaehler[zustand] += 1
        eintrag = {"node_id": str(k.id), "nr": nr, "titel": _text(k.title, nr), "zustand": zustand,
                   "lernsequenzen": sorted(ls_titel[i] for i in voll.get(k.id, set()) | teil.get(k.id, set()))}
        if zustand != VERKNUEPFT and (andere := anderswo.get(k.id)):
            eintrag["anderswo"] = andere
            if zustand == FEHLT:
                zaehler["fehlt_anderswo"] += 1
        gruppen.setdefault(meta.get("thematische_gruppe") or "", []).append(eintrag)

    pk_gruppen: dict[str, list[dict]] = {}
    for k in sorted(pks, key=lambda k: _sortschluessel((k.metadata_ or {}).get("kompetenz_nr"))):
        meta = k.metadata_ or {}
        nr = meta.get("kompetenz_nr")
        pk_gruppen.setdefault(meta.get("thematische_gruppe") or "", []).append(
            {"node_id": str(k.id), "nr": nr, "titel": _text(k.title, nr),
             "anzahl": len(gefoerdert.get(k.id, ()))})

    im_band = {k.id for k in iks}
    fremde_ids = [z for z in set(voll) | set(teil) if z not in im_band]
    ausserhalb = []
    if fremde_ids:
        for k in (await db.execute(sa.select(ContextNode).where(ContextNode.id.in_(fremde_ids)))).scalars():
            nr = (k.metadata_ or {}).get("kompetenz_nr")
            ausserhalb.append({"node_id": str(k.id), "nr": nr, "titel": _text(k.title, nr),
                               "bp_version": k.bp_version, "min_grade": k.min_grade, "max_grade": k.max_grade})
        ausserhalb.sort(key=lambda e: _sortschluessel(e["nr"]))

    return {
        **leer,
        "ik": {"gesamt": len(iks), **zaehler,
               "gruppen": [{"titel": t, "kompetenzen": ks} for t, ks in gruppen.items()]},
        "pk": {"gesamt": len(pks), "genutzt": sum(1 for k in pks if gefoerdert.get(k.id)),
               "gruppen": [{"titel": t, "kompetenzen": ks} for t, ks in pk_gruppen.items()]},
        "ausserhalb": ausserhalb,
        "hinweis": None if iks else "Für Fach, Fassung und Stufen dieses Curriculums sind keine "
                                    "inhaltsbezogenen Kompetenzen im Bildungsplan hinterlegt.",
    }


async def _anderswo(db: AsyncSession, cur: ContextNode, bp: str, ik_ids: list[UUID]) -> dict[UUID, list[str]]:
    """Je IK des Bands die Titel der **anderen veröffentlichten** Curricula desselben Fachs und
    derselben Fassung, die sie (voll oder partiell) verknüpfen."""
    if not ik_ids:
        return {}
    andere = aliased(ContextNode)
    kap, ls = aliased(ContextNode), aliased(ContextNode)
    e_kap, e_ls, e_ik = (aliased(ContextEdge) for _ in range(3))
    bedingungen = [
        andere.content_type == "curriculum", andere.status == "active", andere.id != cur.id,
        andere.subject_id == cur.subject_id,
        sa.func.coalesce(andere.metadata_["bp_version"].as_string(), andere.bp_version) == bp,
    ]
    # Keine Bedingung an die Stufen der anderen Curricula: Klasse 8 und Klasse 9 überschneiden
    # sich nie, teilen aber das Band 8–10. Zum Band gehört, was eine IK des Bands verknüpft.
    zeilen = (await db.execute(
        sa.select(e_ik.to_node_id, andere.title).distinct()
        .select_from(andere)
        .join(e_kap, sa.and_(e_kap.to_node_id == andere.id, e_kap.relation == "part_of"))
        .join(kap, sa.and_(kap.id == e_kap.from_node_id, kap.content_type == "kapitel", kap.status == "active"))
        .join(e_ls, sa.and_(e_ls.to_node_id == kap.id, e_ls.relation == "part_of"))
        .join(ls, sa.and_(ls.id == e_ls.from_node_id, ls.content_type == "lernsequenz", ls.status == "active"))
        .join(e_ik, sa.and_(e_ik.from_node_id == ls.id, e_ik.relation == "references"))
        .where(*bedingungen, e_ik.to_node_id.in_(ik_ids))
    )).all()
    aus: dict[UUID, list[str]] = {}
    for ik_id, titel in zeilen:
        aus.setdefault(ik_id, []).append(titel)
    return {k: sorted(v) for k, v in aus.items()}
