"""Testwelt für die Vernetzung der Fächer (Päckchen BE, Schritt 8) — nur für Dev.

Die echten Curricula geben kaum Bezüge her (Dev: 3 Kapitelpaare, Prod: 10). Dieses Skript legt
**Entwürfe** an, deren Bezüge aus den echten Querverweisen des Bildungsplans entstehen:

- je Fach und Klasse 7–9 ein Curriculum in der Fassung, die der Editionsfahrplan für Stufe und
  laufendes Schuljahr vorsieht;
- Kapitel aus den Kompetenzen der Unterbereiche (`leitidee`) des Bands, je etwa vier Kompetenzen,
  die Kapitel eines Bands der Reihe nach auf seine Klassen verteilt; jede Lernsequenz verweist
  (`references`) auf die Kompetenzen ihres Kapitels — so greifen die `related_to`-Kanten;
- einige Absprachen zwischen Fächern (eingehaltene und, über die Pläne, verletzte);
- Jahresverlaufspläne als Entwürfe für einen Teil der Fächer und Stufen, der Rest bleibt geschätzt.

Alles trägt `owner_pseudonym = dev-testwelt` und „[Testwelt]“ im Titel; `--entfernen` löscht es
wieder (Kanten gehen per CASCADE mit). Weil es Entwürfe sind, erscheint die Testwelt nur mit dem
Schalter „mit Entwürfen“; dann tritt sie an die Stelle veröffentlichter Curricula derselben Stufe.

Aufruf (aus `backend/`):
    venv/bin/python scripts/vernetzung_testwelt.py            # anlegen (vorher Altes entfernen)
    venv/bin/python scripts/vernetzung_testwelt.py --entfernen
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
import uuid
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlalchemy as sa  # noqa: E402

from app.config import settings  # noqa: E402
from app.context import verlaufsplan as vp  # noqa: E402
from app.context.editions import aktive_bp_version, parse_schuljahr_start  # noqa: E402
from app.db.models import ContextEdge, ContextNode, Subject  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402

BESITZER = "dev-testwelt"
STUFEN = (7, 8, 9)
#: Fach → Wochenstunden (Annahme für die Schätzung)
FAECHER = {"D": 4, "M": 4, "E1": 4, "F2": 3, "L2": 3, "G": 2, "GEO": 2, "GK": 1, "WBS": 1, "BIO": 2, "PH": 2,
           "CH": 2, "NWT": 3, "RRK": 2, "REV": 2, "ETH": 2, "MUS": 2, "BK": 2, "SPO": 3}
JE_KAPITEL = 4
#: Pläne (Entwurf, laufendes Schuljahr); vorhandene Pläne bleiben, die Stufe wird dann übersprungen
PLAENE = [("M", 8), ("PH", 8), ("D", 7), ("G", 8), ("BIO", 7), ("E1", 9)]
#: Absprachen in Kl. 8: (Fach mit der Absprache, Kapitel-Nr., anderes Fach, Kapitel-Nr., Art, Text)
ABSPRACHEN = [
    ("PH", 1, "M", 1, "vorher", "Lineare Zusammenhänge vor den Bewegungen"),
    ("PH", 2, "M", 5, "vorher", "Gleichungen umstellen, bevor Kräfte berechnet werden"),   # liegt später → verletzt
    ("CH", 1, "PH", 1, "gleichzeitig", "Teilchenvorstellung gemeinsam"),
    ("G", 2, "D", 2, "abgestimmt", "Quellentexte im Deutschunterricht vorbereiten"),
    ("GEO", 1, "BIO", 1, "gleichzeitig", "Ökosysteme parallel"),
    ("E1", 1, "D", None, "abgestimmt", "Grammatikbegriffe einheitlich"),
]


def _nr_schluessel(t: str) -> list:
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", t or "")]


def _knoten(typ, titel, fach, *, status=vp.ENTWURF, meta=None, stufen=(None, None)) -> ContextNode:
    return ContextNode(id=uuid.uuid4(), category="knowledge", content_type=typ, title=titel, status=status,
                       owner_pseudonym=BESITZER, read_scope="school", write_scope="private", subject_id=fach,
                       min_grade=stufen[0], max_grade=stufen[1], metadata_=meta or {})


async def entfernen(db) -> int:
    n = (await db.execute(sa.delete(ContextNode).where(ContextNode.owner_pseudonym == BESITZER))).rowcount
    await db.commit()
    return n


async def _kapitelgruppen(db, fach_id: int, version: str, stufe: int) -> list[tuple[str, list]]:
    """Kompetenzen der Unterbereiche des Bands, das `stufe` enthält, in Gruppen zu je
    `JE_KAPITEL` — nur die Gruppen, die auf `stufe` fallen."""
    from sqlalchemy.orm import aliased

    ik = aliased(ContextNode)
    zeilen = (await db.execute(
        sa.select(ContextNode, ik.id, ik.metadata_)
        .join(ContextEdge, sa.and_(ContextEdge.to_node_id == ContextNode.id, ContextEdge.relation == "part_of"))
        .join(ik, sa.and_(ik.id == ContextEdge.from_node_id, ik.content_type == "ik_kompetenz", ik.status == "active"))
        .where(ContextNode.content_type == "leitidee", ContextNode.status == "active",
               ContextNode.subject_id == fach_id, ContextNode.bp_version == version,
               ContextNode.min_grade <= stufe, ContextNode.max_grade >= stufe))).all()
    if not zeilen:
        return []
    band = (min(l.min_grade for l, *_ in zeilen), max(l.max_grade for l, *_ in zeilen))
    je_bereich: dict = defaultdict(list)
    bereiche = {}
    for l, ik_id, ik_meta in zeilen:
        bereiche[l.id] = l
        je_bereich[l.id].append((ik_id, (ik_meta or {}).get("kompetenz_nr") or ""))
    gruppen = []
    for bid in sorted(bereiche, key=lambda b: _nr_schluessel((bereiche[b].metadata_ or {}).get("nr") or bereiche[b].title)):
        iks = sorted(je_bereich[bid], key=lambda x: _nr_schluessel(x[1]))
        titel = re.sub(r"^\s*[\d.]+\s*", "", bereiche[bid].title)[:60] or bereiche[bid].title[:60]
        teile = [iks[i:i + JE_KAPITEL] for i in range(0, len(iks), JE_KAPITEL)]
        for n, teil in enumerate(teile, start=1):
            gruppen.append((f"{titel} {n}" if len(teile) > 1 else titel, teil))
    stufen = list(range(band[0], band[1] + 1))
    k = len(stufen)
    return [g for i, g in enumerate(gruppen) if stufen[min(k - 1, i * k // len(gruppen))] == stufe]


async def anlegen(db) -> dict:
    schuljahr = vp.aktuelles_schuljahr()
    start = parse_schuljahr_start(schuljahr)
    faecher = {s.fach_code: s for s in (await db.execute(sa.select(Subject).where(
        Subject.fach_code.in_(list(FAECHER))))).scalars()}
    versionen: dict = defaultdict(set)
    for f, v in (await db.execute(sa.select(ContextNode.subject_id, ContextNode.bp_version).where(
            ContextNode.subject_id.in_([s.id for s in faecher.values()]), ContextNode.content_type == "ik_kompetenz",
            ContextNode.bp_version != "").distinct())).all():
        versionen[f].add(v)

    kapitel: dict[tuple[str, int], list[ContextNode]] = {}
    zahl = defaultdict(int)
    for code, ws in FAECHER.items():
        fach = faecher.get(code)
        if fach is None:
            continue
        for stufe in STUFEN:
            if fach.min_grade and stufe < fach.min_grade:
                continue
            version = aktive_bp_version(stufe, versionen[fach.id], start)
            gruppen = await _kapitelgruppen(db, fach.id, version, stufe) if version else []
            if not gruppen:
                continue
            cur = _knoten("curriculum", f"[Testwelt] {fach.name} Kl. {stufe}", fach.id, stufen=(stufe, stufe),
                          meta={"bp_version": version, "jahrgangsstufe": str(stufe), "testwelt": True,
                                "rahmen": {"wochenstunden": {str(stufe): ws}}})
            db.add(cur)
            std = max(2, round(30 * ws / len(gruppen)))
            liste = []
            for nr, (titel, iks) in enumerate(gruppen, start=1):
                k = _knoten("kapitel", titel, fach.id, meta={"reihenfolge": nr, "std": std})
                ls = _knoten("lernsequenz", f"{titel} — Sequenz", fach.id, meta={
                    "reihenfolge": 1, "std": std,
                    "eintraege": [{"ik": [{"node_id": str(i), "nr": n} for i, n in iks]}]})
                db.add_all([k, ls])
                await db.flush()
                db.add_all([ContextEdge(from_node_id=k.id, to_node_id=cur.id, relation="part_of", metadata_={}),
                            ContextEdge(from_node_id=ls.id, to_node_id=k.id, relation="part_of", metadata_={})]
                           + [ContextEdge(from_node_id=ls.id, to_node_id=i, relation="references", metadata_={})
                              for i, _ in iks])
                liste.append(k)
            kapitel[(code, stufe)] = liste
            zahl["curricula"] += 1
            zahl["kapitel"] += len(liste)
    await db.flush()

    # Absprachen (Kl. 8)
    for von, vnr, zu, znr, art, text in ABSPRACHEN:
        kv, kz = kapitel.get((von, 8)), kapitel.get((zu, 8))
        if not kv or len(kv) < vnr or (kz is None) or (znr and len(kz) < znr):
            continue
        ziel = kz[znr - 1] if znr else None
        a = {"id": str(uuid.uuid4()), "fach_code": zu, "kapitel_id": str(ziel.id) if ziel else None,
             "kapitel_titel": ziel.title if ziel else None, "art": art, "text": text}
        k = kv[vnr - 1]
        k.metadata_ = {**k.metadata_, "absprachen": [*(k.metadata_.get("absprachen") or []), a]}
        zahl["absprachen"] += 1

    # Pläne (Entwurf), Abschnitte der Reihe nach, Dauer aus Stunden ÷ Wochenstunden
    vorhanden = {(s, g) for s, g in (await db.execute(sa.select(ContextNode.subject_id, ContextNode.min_grade).where(
        ContextNode.content_type == vp.TYP, ContextNode.status.in_(vp.LESBAR),
        ContextNode.metadata_["schuljahr"].as_string() == schuljahr))).all()}
    for code, stufe in PLAENE:
        liste = kapitel.get((code, stufe))
        fach = faecher.get(code)
        if not liste or (fach.id, stufe) in vorhanden:
            continue
        ws = FAECHER[code]
        abschnitte = [{"id": uuid.uuid4().hex[:12], "titel": k.title, "notiz": "", "puffer": False,
                       "wochen": max(1, round((k.metadata_.get("std") or ws) / ws)),
                       "kapitel_ids": [str(k.id)], "sequenz_ids": []} for k in liste]
        db.add(_knoten(vp.TYP, f"[Testwelt] Jahresverlaufsplan {fach.name} Kl. {stufe}", fach.id,
                       stufen=(stufe, stufe), meta={"schuljahr": schuljahr, "planungsart": "kapitel",
                                                    "abschnitte": abschnitte}))
        zahl["plaene"] += 1
    await db.commit()
    return dict(zahl)


async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--entfernen", action="store_true", help="nur die Testwelt löschen")
    args = p.parse_args()
    if settings.environment == "production":
        sys.exit("Nicht auf der Produktion.")
    async with AsyncSessionLocal() as db:
        weg = await entfernen(db)
        print(f"Entfernt: {weg} Knoten der Testwelt")
        if not args.entfernen:
            print("Angelegt:", await anlegen(db))


if __name__ == "__main__":
    asyncio.run(main())
