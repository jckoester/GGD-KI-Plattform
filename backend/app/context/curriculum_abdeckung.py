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

**Was zählt.** Die Spalten IK und PK der Einträge (`eintraege[].ik`, `eintraege[].pk` mit
`node_id`, bei IK `partiell`) — nicht die Kanten. Aus den Einträgen schreibt der Editor die
Kanten, aber auch Verweise **in den Hinweisen** (Kompetenzen anderer Fächer) werden zu
`references`-Kanten; an der Kante allein ist ein gewollter Fachbezug von einem Fehler nicht zu
unterscheiden.

**Was gesondert steht.** `ausserhalb`: verknüpfte Kompetenzen des eigenen Fachs aus anderem Band
oder anderer Fassung (etwa nach einem Fassungswechsel). `fremdes_fach`: Kompetenzen eines
**anderen Fachs** in den Spalten IK und PK — ein Fehler, kein Bezug: Bis 25.08.2026 löste der
Import PK-Nummern ohne Fach auf (`resolve_pk_node`), ein Mathematik-Curriculum hing danach an
den PK von Kunst, Geographie, Chemie … Reparatur: `scripts/curriculum_kompetenzen_reparieren.py`.

**Leitlinien der Schule** (0.50, Päckchen AT): je Leitlinie, welche ihrer Aspekte in welchen
Lernsequenzen vorkommen — aus den Verweisen `lb:`/`lba:` **in den Hinweisen**. Nur zur
Information, ohne Pflicht (Plan F5): Eine Leitlinie muss nicht in jedem Curriculum stehen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.context.bp_baender import Band, band_schluessel, band_zuordnen, baender_aus
from app.context.editions import BP_STATUS_CURRICULUM
from app.db.models import ContextEdge, ContextNode, Subject

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


def _eintraege(tree: dict):
    for kap in tree.get("kapitel", []):
        for ls in kap.get("lernsequenzen", []):
            yield str(ls["id"]), ((ls.get("metadata") or {}).get("eintraege") or [])


def _uuid(ref) -> UUID | None:
    try:
        return UUID(str(ref.get("node_id"))) if isinstance(ref, dict) and ref.get("node_id") else None
    except ValueError:
        return None


def _bp_version(cur: ContextNode) -> str | None:
    return (cur.metadata_ or {}).get("bp_version") or cur.bp_version


async def kompetenzen_der_fassung(db: AsyncSession, subject_id: int, bp: str,
                                  typ: str = "ik_kompetenz") -> list[ContextNode]:
    """IK (oder PK) eines Fachs in einer Fassung, ohne Stufenfilter.

    Geltende oder kommende Fassung (0.46): nur deren Knoten — archivierte daneben sind
    abgelöste Doppel (alte `bp_id`-Schreibweise). Eine abgelöste Fassung hat nur archivierte;
    dann zählen die.
    """
    fassung = sa.and_(ContextNode.subject_id == subject_id, ContextNode.bp_version == bp)
    lebt = (await db.execute(sa.select(sa.exists().where(
        fassung, ContextNode.status.in_(BP_STATUS_CURRICULUM),
        ContextNode.content_type.in_(("ik_kompetenz", "pk_kompetenz")))))).scalar()
    im_fach = sa.and_(fassung, ContextNode.status.in_(BP_STATUS_CURRICULUM) if lebt
                      else ContextNode.status != "deleted")
    return list((await db.execute(sa.select(ContextNode).where(
        ContextNode.content_type == typ, im_fach))).scalars().all())


@dataclass
class BandDesCurriculums:
    iks: list[ContextNode]
    pks: list[ContextNode]
    band: Band | None = None                      # zugeordnet (gewählt oder eindeutig)
    kandidaten: list[Band] = field(default_factory=list)   # Bänder, die die Stufen berühren


async def band_des_curriculums(db: AsyncSession, cur: ContextNode) -> BandDesCurriculums:
    """IK des Bands, PK des Fachs und das Band des Curriculums (0.46, Schritt 8).

    Zum Band gehören die IK unter seiner Überschrift im Bildungsplan (`bp_baender`). Ohne
    Zuordnung (parallele Bänder der Oberstufe ohne `metadata.band`) die IK aller Bänder, die
    die Stufen berühren — wie bis 0.45, als nur die Stufen zählten. Leer ohne Fach oder Fassung.
    """
    bp = _bp_version(cur)
    if cur.subject_id is None or not bp:
        return BandDesCurriculums([], [])
    alle = await kompetenzen_der_fassung(db, cur.subject_id, bp)
    band, kandidaten = band_zuordnen(baender_aus(alle), cur.min_grade, cur.max_grade,
                                     (cur.metadata_ or {}).get("band"))
    schluessel = {band.schluessel} if band else {b.schluessel for b in kandidaten}

    def gehoert_dazu(k: ContextNode) -> bool:
        if (s := band_schluessel(k.metadata_)) is not None:
            return s in schluessel
        # Ohne Bandüberschrift im Pfad (im Bestand keine, Stand 17.11.2026): nach Stufen.
        lo, hi = cur.min_grade, cur.max_grade
        return (lo is None or hi is None
                or ((k.min_grade is None or k.min_grade <= hi) and (k.max_grade is None or k.max_grade >= lo)))

    iks = [k for k in alle if gehoert_dazu(k)]
    pks = await kompetenzen_der_fassung(db, cur.subject_id, bp, "pk_kompetenz")
    return BandDesCurriculums(iks, pks, band, kandidaten)


async def baender_fuer(db: AsyncSession, subject_id: int, bp: str, min_grade: int | None,
                       max_grade: int | None, gewaehlt: str | None = None) -> tuple[Band | None, list[Band]]:
    """Band und Kandidaten für Fach, Fassung und Stufen — zum Anlegen und Ändern von `band`."""
    return band_zuordnen(baender_aus(await kompetenzen_der_fassung(db, subject_id, bp)),
                         min_grade, max_grade, gewaehlt)


async def kompetenzen_des_bands(db: AsyncSession, cur: ContextNode) -> tuple[list[ContextNode], list[ContextNode]]:
    """IK des Bands und PK des Fachs in der Fassung des Curriculums — dieselbe Menge für
    Abdeckung und Assistent (`get_bp_competences`). Leer ohne Fach oder Fassung."""
    b = await band_des_curriculums(db, cur)
    return b.iks, b.pks


def bereich_von(meta: dict) -> str:
    """Der Bereich einer Kompetenz: `thematische_gruppe`, sonst die letzte Überschrift im
    `breadcrumb` (etwa „3.1.7 Optik“). `thematische_gruppe` ist in den meisten Fächern leer
    (Stand 16.11.2026 nur Mathematik V3 und einzelne V3-Fassungen); ohne Rückfall fiele dort
    alles in einen Bereich ohne Namen."""
    if gruppe := (meta.get("thematische_gruppe") or "").strip():
        return gruppe
    pfad = meta.get("breadcrumb")
    return str(pfad[-1]).strip() if isinstance(pfad, list) and pfad else ""


def verknuepfungen(tree: dict) -> tuple[dict[UUID, set[str]], dict[UUID, set[str]], dict[UUID, set[str]]]:
    """Spalten IK und PK der Einträge: je Kompetenz die Lernsequenzen — IK voll, IK partiell, PK."""
    voll: dict[UUID, set[str]] = {}
    teil: dict[UUID, set[str]] = {}
    gefoerdert: dict[UUID, set[str]] = {}
    for ls_id, eintraege in _eintraege(tree):
        for e in eintraege:
            for ref in e.get("ik") or []:
                if k_id := _uuid(ref):
                    (teil if ref.get("partiell") is True else voll).setdefault(k_id, set()).add(ls_id)
            for ref in e.get("pk") or []:
                if k_id := _uuid(ref):
                    gefoerdert.setdefault(k_id, set()).add(ls_id)
    return voll, teil, gefoerdert


_LB_VERWEIS = re.compile(r"@\[[^\]]*\]\((lba|lb):([0-9a-f-]{36})\)")


async def leitlinien_abdeckung(db: AsyncSession, tree: dict) -> list[dict]:
    """Je aktive Leitlinie der Schule: ihre Aspekte mit den Lernsequenzen, die auf sie verweisen.

    `ganz`: Lernsequenzen, die auf die Leitlinie als Ganzes verweisen (`lb:`). Ohne Leitlinien
    eine leere Liste — die Oberfläche zeigt dann nichts.
    """
    from app.context.leitlinien import alle_leitlinien

    leitlinien = await alle_leitlinien(db)
    if not leitlinien:
        return []
    ls_titel = _lernsequenzen(tree)
    treffer: dict[str, set[str]] = {}
    for ls_id, eintraege in _eintraege(tree):
        for e in eintraege:
            for m in _LB_VERWEIS.finditer(e.get("hinweise") or ""):
                treffer.setdefault(m.group(2), set()).add(ls_id)

    def lss(node_id) -> list[str]:
        return sorted(ls_titel[i] for i in treffer.get(str(node_id), ()))

    aus = []
    for l in leitlinien:
        aspekte = [{"node_id": str(a.id), "kuerzel": a.kuerzel, "titel": a.titel,
                    "lernsequenzen": lss(a.id)} for a in l.aspekte]
        aus.append({"node_id": str(l.id), "kuerzel": l.kuerzel, "titel": l.titel,
                    "ganz": lss(l.id), "aspekte": aspekte,
                    "vorkommend": sum(1 for a in aspekte if a["lernsequenzen"])})
    return aus


async def abdeckung(db: AsyncSession, tree: dict) -> dict:
    """Die Abdeckung für einen Baum aus `load_curriculum_tree` (Rechte prüft der Aufrufer)."""
    cur = await db.get(ContextNode, tree["id"])
    bp = _bp_version(cur)
    ls_titel = _lernsequenzen(tree)
    leer = {"leitlinien": await leitlinien_abdeckung(db, tree),
            "bp_version": bp, "min_grade": cur.min_grade, "max_grade": cur.max_grade,
            "ik": {"gesamt": 0, VERKNUEPFT: 0, PARTIELL: 0, FEHLT: 0, "fehlt_anderswo": 0, "gruppen": []},
            "pk": {"gesamt": 0, "genutzt": 0, "gruppen": []}, "ausserhalb": [], "fremdes_fach": [],
            "band": None, "baender_zur_wahl": [], "hinweis": None}
    if cur.subject_id is None or not bp:
        return {**leer, "hinweis": "Fach oder Bildungsplan-Fassung des Curriculums fehlen."}
    bd = await band_des_curriculums(db, cur)
    iks, pks = bd.iks, bd.pks
    # Parallele Bänder ohne Wahl (Oberstufe): gemessen wird gegen alle, die Wahl steht offen.
    zur_wahl = [b.als_dict() for b in bd.kandidaten] if len(bd.kandidaten) > 1 else []

    voll, teil, gefoerdert = verknuepfungen(tree)

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
        gruppen.setdefault(bereich_von(meta), []).append(eintrag)

    pk_gruppen: dict[str, list[dict]] = {}
    for k in sorted(pks, key=lambda k: _sortschluessel((k.metadata_ or {}).get("kompetenz_nr"))):
        meta = k.metadata_ or {}
        nr = meta.get("kompetenz_nr")
        pk_gruppen.setdefault(bereich_von(meta), []).append(
            {"node_id": str(k.id), "nr": nr, "titel": _text(k.title, nr),
             "anzahl": len(gefoerdert.get(k.id, ()))})

    # Verknüpft, aber nicht unter den Kompetenzen des Bands: anderes Band, andere Fassung oder
    # ein anderes Fach.
    bekannt = {k.id for k in iks} | {k.id for k in pks}
    rest = {z: lss for quelle in (voll, teil, gefoerdert) for z, lss in quelle.items() if z not in bekannt}
    ausserhalb, fremdes_fach = [], []
    if rest:
        faecher = dict((await db.execute(sa.select(Subject.id, Subject.name))).all())
        for k in (await db.execute(sa.select(ContextNode).where(ContextNode.id.in_(list(rest))))).scalars():
            nr = (k.metadata_ or {}).get("kompetenz_nr")
            lss = set().union(*(q.get(k.id, set()) for q in (voll, teil, gefoerdert)))
            zeile = {"node_id": str(k.id), "typ": "pk" if k.content_type == "pk_kompetenz" else "ik",
                     "nr": nr, "titel": _text(k.title, nr), "bp_version": k.bp_version,
                     "lernsequenzen": sorted(ls_titel[i] for i in lss)}
            if k.subject_id != cur.subject_id:
                fremdes_fach.append({**zeile, "fach": faecher.get(k.subject_id, "ohne Fach")})
            else:
                ausserhalb.append(zeile)
        ausserhalb.sort(key=lambda e: (e["typ"], _sortschluessel(e["nr"])))
        fremdes_fach.sort(key=lambda e: (e["fach"], e["typ"], _sortschluessel(e["nr"])))

    return {
        **leer,
        "ik": {"gesamt": len(iks), **zaehler,
               "gruppen": [{"titel": t, "kompetenzen": ks} for t, ks in gruppen.items()]},
        "pk": {"gesamt": len(pks), "genutzt": sum(1 for k in pks if gefoerdert.get(k.id)),
               "gruppen": [{"titel": t, "kompetenzen": ks} for t, ks in pk_gruppen.items()]},
        "ausserhalb": ausserhalb,
        "fremdes_fach": fremdes_fach,
        "band": bd.band.als_dict() if bd.band else None,
        "baender_zur_wahl": zur_wahl,
        "hinweis": ("Für Fach, Fassung und Stufen dieses Curriculums sind keine inhaltsbezogenen "
                    "Kompetenzen im Bildungsplan hinterlegt." if not iks else
                    "Zu diesen Stufen gibt es im Bildungsplan mehrere Bänder ("
                    + ", ".join(b["schluessel"] for b in zur_wahl) + "). Ordne das Curriculum im "
                    "Editor einem Band zu — bis dahin zählen die Kompetenzen aller dieser Bänder."
                    if zur_wahl and bd.band is None else None),
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
