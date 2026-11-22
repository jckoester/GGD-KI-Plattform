"""Schulweite Übersicht einer Leitlinie (0.53, Päckchen AU).

Wo kommt welcher Aspekt einer Leitlinie der Schule im Unterricht vor — in welchem Fach,
Curriculum, Kapitel und welcher Lernsequenz —, und welcher nirgends? AT zeigt das je
Curriculum (`leitlinien_abdeckung`); hier über alle Curricula, die die Person lesen darf.

**Daten.** Ein Verweis im Feld `hinweise` (`@[…](lba:<uuid>)`, `lb:` für die Leitlinie als
Ganzes) hat eine Kante `references` von der Lernsequenz zum Ziel; Editor, Import und
Curriculum-Assistent legen sie beim Speichern an. Die Abfrage geht über die Kette
Lernsequenz → Kapitel → Curriculum (`part_of`), keine neue Speicherung. Auf Dev stimmten
Token und Kanten am 22.11.2026 überein (17 Lernsequenzen, 35 Kanten, keine Abweichung).

**Was zählt (F3, neu entschieden 22.11.2026 mit AZ).** Veröffentlichte Curricula und — für
alle, die Entwürfe lesen dürfen (`darf_entwurf_lesen`) — Entwürfe, gekennzeichnet über
`status`. Ein Entwurf, der ein veröffentlichtes Curriculum ersetzen soll (`kopie_von`), tritt
an dessen Stelle, wie in der Bandabdeckung mit Entwürfen: Sonst zählte dieselbe Lernsequenz
zweimal, und das Raster zeigte doppelt so viele Fundstellen, wie es nach dem Veröffentlichen
gibt. ``nur_veroeffentlicht`` zeigt den gültigen Stand. Archivierte oder gelöschte Teile und
Aspekte zählen nicht.

**Leitperspektiven (F1).** Dieselbe Übersicht gilt für die Leitperspektiven des Bildungsplans
(`leitperspektive`, Aspekte `leitperspektive_aspekt`). Ihre Verweise (`lp:`/`lpa:`) tragen
dieselben Kanten; nur der Baum entsteht anders — der Aspekt hängt per `part_of` an seiner
Leitperspektive (statt über ein Kürzel), sein Kürzel ist die `bp_id` („BNE_07“).

**Leitfaden Demokratiebildung (0.53.1, F2).** Der LFDB hängt als Leitperspektive mit drei
Ebenen im Baum: Baustein (4) → Themenblock (11) → Kompetenz (60), alles `part_of`. Seine
Spalten sind die Themenblöcke („B1.T2“). Ein Verweis auf eine Kompetenz zählt bei ihrem
Themenblock, einer auf einen Baustein oder den LFDB als Ganzes unter „Ganz“. Verweist eine
Lernsequenz auf mehrere Ziele derselben Spalte, ist das eine Fundstelle.
"""
from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.context.curriculum_entwurf import ENTWURF, darf_entwurf_lesen
from app.context.leitlinien import (
    LEITLINIE, Aspekt, Leitlinie, _natuerlich, alle_leitlinien, lfdb_anzeige, lfdb_kuerzel,
)
from app.db.models import ContextEdge, ContextNode, Subject

LEITPERSPEKTIVE = "leitperspektive"
LP_ASPEKT = "leitperspektive_aspekt"

#: Wie in `_lesbare_curricula`: Nur `private` schränkt ein.
_OFFEN = ("global", "school", "subject")


def _stufen(min_grade, max_grade) -> str | None:
    if min_grade is None and max_grade is None:
        return None
    if min_grade == max_grade or max_grade is None:
        return str(min_grade)
    if min_grade is None:
        return str(max_grade)
    return f"{min_grade}–{max_grade}"


async def leitlinien_fundstellen(db: AsyncSession, ziel_ids: list[UUID], user, *,
                      nur_veroeffentlicht: bool = False) -> list[dict]:
    """Je Verweis einer lesbaren Lernsequenz auf eines der Ziele eine Fundstelle."""
    if not ziel_ids:
        return []
    from app.auth.vorschau import eigenes_zaehlt

    status = ["active"] if nur_veroeffentlicht or not darf_entwurf_lesen(user) else ["active", ENTWURF]
    cur, kap, ls = aliased(ContextNode), aliased(ContextNode), aliased(ContextNode)
    e_ls, e_kap, e_ziel = aliased(ContextEdge), aliased(ContextEdge), aliased(ContextEdge)
    zeilen = (await db.execute(
        sa.select(e_ziel.to_node_id, ls.id, ls.title, kap.id, kap.title, kap.metadata_["reihenfolge"].as_integer(),
                  cur.id, cur.title, cur.status, cur.metadata_, cur.bp_version, cur.min_grade,
                  cur.max_grade, Subject.id, Subject.name)
        .select_from(e_ziel)
        .join(ls, sa.and_(ls.id == e_ziel.from_node_id, ls.content_type == "lernsequenz"))
        .join(e_ls, sa.and_(e_ls.from_node_id == ls.id, e_ls.relation == "part_of"))
        .join(kap, sa.and_(kap.id == e_ls.to_node_id, kap.content_type == "kapitel"))
        .join(e_kap, sa.and_(e_kap.from_node_id == kap.id, e_kap.relation == "part_of"))
        .join(cur, sa.and_(cur.id == e_kap.to_node_id, cur.content_type == "curriculum"))
        .outerjoin(Subject, Subject.id == cur.subject_id)
        .where(
            e_ziel.relation == "references",
            e_ziel.to_node_id.in_(ziel_ids),
            cur.status.in_(status),
            # Teile tragen den Status ihres Curriculums; ein archiviertes Kapitel zählt nicht.
            kap.status == cur.status,
            ls.status == cur.status,
            sa.or_(cur.read_scope.in_(_OFFEN),
                   sa.and_(sa.literal(eigenes_zaehlt(user.sub)), cur.owner_pseudonym == user.sub)),
        )
    )).all()

    aus = [{
        "ziel_id": str(ziel), "lernsequenz_id": str(ls_id), "lernsequenz": ls_titel,
        "kapitel_id": str(kap_id), "kapitel": kap_titel, "_kapitel_ordnung": kap_ordnung,
        "curriculum_id": str(cur_id), "curriculum": cur_titel, "status": cur_status,
        "bp_version": (meta or {}).get("bp_version") or bp, "stufen": _stufen(min_g, max_g),
        "min_grade": min_g, "max_grade": max_g,
        "fach_id": fach_id, "fach": fach_name,
        "_kopie_von": (meta or {}).get("kopie_von") if cur_status == ENTWURF else None,
    } for (ziel, ls_id, ls_titel, kap_id, kap_titel, kap_ordnung, cur_id, cur_titel, cur_status,
           meta, bp, min_g, max_g, fach_id, fach_name) in zeilen]

    # Ein Entwurf mit `kopie_von` ersetzt sein Original — auch dann, wenn er (noch) keine
    # Fundstelle hat: Dann verschwindet die Leitlinie im geplanten Stand aus diesem Curriculum.
    ersetzt = {f["_kopie_von"] for f in aus if f["_kopie_von"]}
    if not nur_veroeffentlicht and darf_entwurf_lesen(user):
        ersetzt |= set((await db.execute(
            sa.select(ContextNode.metadata_["kopie_von"].astext).where(
                ContextNode.content_type == "curriculum", ContextNode.status == ENTWURF,
                ContextNode.metadata_["kopie_von"].astext.isnot(None)))).scalars())
    aus = [f for f in aus if f["curriculum_id"] not in ersetzt]
    aus.sort(key=lambda f: (f["fach"] or "", f["min_grade"] or 0, f["curriculum"],
                            f["_kapitel_ordnung"] or 0, f["kapitel"], f["lernsequenz"]))
    for f in aus:
        del f["_kopie_von"], f["_kapitel_ordnung"]
    return aus


async def _teile(db: AsyncSession, eltern_ids, typ: str) -> list[ContextNode]:
    """Aktive Knoten des Typs, die per `part_of` an einem der Eltern hängen."""
    if not eltern_ids:
        return []
    return list((await db.execute(
        sa.select(ContextNode).join(ContextEdge, sa.and_(
            ContextEdge.from_node_id == ContextNode.id, ContextEdge.relation == "part_of"))
        .where(ContextEdge.to_node_id.in_(list(eltern_ids)), ContextNode.content_type == typ,
               ContextNode.status == "active"))).scalars().all())


async def _leitperspektive(db: AsyncSession, knoten: ContextNode) -> Leitlinie:
    """Eine Leitperspektive mit ihren aktiven Aspekten (über `part_of`), nach Kürzel."""
    from app.context.service import leitperspektive_code

    aspekte = await _teile(db, [knoten.id], LP_ASPEKT)
    liste = [Aspekt(a.id, str((a.metadata_ or {}).get("bp_id") or "").upper(), a.title) for a in aspekte]
    liste.sort(key=lambda a: _natuerlich(a.kuerzel))
    return Leitlinie(knoten.id, leitperspektive_code(knoten.metadata_), knoten.title, liste)


async def _lfdb(db: AsyncSession, knoten: ContextNode) -> tuple[Leitlinie, dict[UUID, UUID | None]]:
    """Der LFDB mit den Themenblöcken als Aspekten und der Zuordnung Ziel → Spalte
    (Themenblock-ID; ``None`` für „Ganz“)."""
    bausteine = await _teile(db, [knoten.id], "lfdb_baustein")
    bloecke = await _teile(db, [b.id for b in bausteine], "lfdb_themenblock")
    spalte: dict[UUID, UUID | None] = {knoten.id: None, **{b.id: None for b in bausteine},
                                       **{t.id: t.id for t in bloecke}}
    if bloecke:
        for kid, tid in (await db.execute(
            sa.select(ContextNode.id, ContextEdge.to_node_id).join(ContextEdge, sa.and_(
                ContextEdge.from_node_id == ContextNode.id, ContextEdge.relation == "part_of"))
            .where(ContextEdge.to_node_id.in_([t.id for t in bloecke]),
                   ContextNode.content_type == "lfdb_kompetenz", ContextNode.status == "active"))).all():
            spalte[kid] = tid
    aspekte = [Aspekt(t.id, lfdb_anzeige(lfdb_kuerzel((t.metadata_ or {}).get("bp_id"))), t.title)
               for t in bloecke]
    aspekte.sort(key=lambda a: _natuerlich(a.kuerzel))
    return Leitlinie(knoten.id, "LFDB", knoten.title, aspekte), spalte


async def leitlinien_uebersicht(db: AsyncSession, leitlinie_id: UUID, user, *,
                     nur_veroeffentlicht: bool = False) -> dict | None:
    """Die Übersicht einer aktiven Leitlinie oder Leitperspektive, oder ``None``, wenn es sie
    nicht gibt.

    - ``art``: ``leitlinie`` oder ``leitperspektive``;

    - ``aspekte``: je aktiver Aspekt die Fundstellen und ``je_fach`` (Fach-ID → Anzahl) fürs
      Raster;
    - ``ganz``: Fundstellen, die auf die Leitlinie als Ganzes verweisen (beim LFDB auch auf
      einen Baustein);
    - ``faecher``: die Fächer mit mindestens einer Fundstelle;
    - ``alle_faecher``: alle Fächer der Schule, ungefiltert (F7) — für den Umschalter „alle
      Fächer“; eine leere Spalte zeigt, welches Fach noch kein Curriculum hat. Beide Listen in
      der Reihenfolge der Schule (`sort_order`, dann Name), damit die Spalten beim Umschalten
      an ihrem Platz bleiben;
    - ``ohne_fundstelle``: Kürzel der Aspekte, die nirgends vorkommen.
    """
    knoten = await db.get(ContextNode, leitlinie_id)
    if knoten is None or knoten.status != "active":
        return None
    from app.context.service import leitperspektive_code

    spalte: dict[UUID, UUID | None] | None = None
    if knoten.content_type == LEITPERSPEKTIVE and leitperspektive_code(knoten.metadata_) == "LFDB":
        leitlinie, spalte = await _lfdb(db, knoten)
    elif knoten.content_type == LEITPERSPEKTIVE:
        leitlinie = await _leitperspektive(db, knoten)
    elif knoten.content_type == LEITLINIE:
        leitlinie = next((l for l in await alle_leitlinien(db) if l.id == knoten.id), None)
        if leitlinie is None:
            return None
    else:
        return None
    if spalte is None:
        spalte = {leitlinie.id: None, **{a.id: a.id for a in leitlinie.aspekte}}
    alle = await leitlinien_fundstellen(db, list(spalte), user, nur_veroeffentlicht=nur_veroeffentlicht)
    # Je Spalte (Aspekt-ID, "ganz") eine Fundstelle je Lernsequenz — beim LFDB fallen mehrere
    # Ziele in eine Spalte.
    nach_ziel: dict[str, list[dict]] = {}
    gesehen: set[tuple[str, str]] = set()
    for f in alle:
        ziel = spalte.get(UUID(f.pop("ziel_id")))
        schluessel = str(ziel) if ziel else "ganz"
        if (schluessel, f["lernsequenz_id"]) in gesehen:
            continue
        gesehen.add((schluessel, f["lernsequenz_id"]))
        nach_ziel.setdefault(schluessel, []).append(f)

    faecher: set[int | None] = set()
    aspekte = []
    for a in leitlinie.aspekte:
        liste = nach_ziel.get(str(a.id), [])
        je_fach: dict[str, int] = {}
        for f in liste:
            faecher.add(f["fach_id"])
            schluessel = str(f["fach_id"])
            je_fach[schluessel] = je_fach.get(schluessel, 0) + 1
        aspekte.append({"node_id": str(a.id), "kuerzel": a.kuerzel, "titel": a.titel,
                        "fundstellen": liste, "je_fach": je_fach})
    ganz = nach_ziel.get("ganz", [])
    faecher |= {f["fach_id"] for f in ganz}
    alle_faecher = [{"id": i, "name": n} for i, n in (await db.execute(
        sa.select(Subject.id, Subject.name).order_by(Subject.sort_order, Subject.name))).all()]
    if None in faecher:  # Curriculum ohne Fach — als letzte Spalte
        alle_faecher.append({"id": None, "name": "ohne Fach"})

    return {
        "art": "leitperspektive" if knoten.content_type == LEITPERSPEKTIVE else "leitlinie",
        "leitlinie": {"node_id": str(leitlinie.id), "kuerzel": leitlinie.kuerzel, "titel": leitlinie.titel},
        "nur_veroeffentlicht": nur_veroeffentlicht or not darf_entwurf_lesen(user),
        "faecher": [f for f in alle_faecher if f["id"] in faecher],
        "alle_faecher": alle_faecher,
        "aspekte": aspekte,
        "ganz": ganz,
        "ohne_fundstelle": [a["kuerzel"] for a in aspekte if not a["fundstellen"]],
    }
