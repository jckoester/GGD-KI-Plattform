"""Einen Curriculum-Entwurf veröffentlichen (0.45, Päckchen AP Teil A, Punkt 7 und 9).

**Übersicht** (`uebersicht`): was vor dem Veröffentlichen auffallen sollte — Stunden,
Abdeckung, als veraltet markierte Kompetenzen, fehlende und mehrdeutige Begriffe, und bei einer
Kopie, was mit dem Vorgänger und den Einheiten geschieht. Sie warnt, sie sperrt nicht.

**Veröffentlichen** (`veroeffentlichen`): Der ganze Baum wird `active`. Ist der Entwurf eine
Kopie (`metadata.kopie_von`) eines veröffentlichten Curriculums, **ersetzt** er es (E15):
- Einheiten **des laufenden Schuljahrs**, die an einem Kapitel des Vorgängers hängen, wandern auf
  das entsprechende Kapitel der Kopie (`kopie_von` am Kapitel). Fehlt es in der Kopie, bleibt die
  Einheit am alten Kapitel; die Planung zeigt dann ein Banner.
- Danach wird der Vorgänger samt Kapiteln und Lernsequenzen archiviert. Einheiten früherer
  Schuljahre bleiben unberührt an ihm hängen.

Wer veröffentlicht, prüft der Router (`darf_veroeffentlichen`); die Veröffentlichung steht im
Audit-Log (`admin.curriculum_published`).

Vektoren: Kapitel aus dem Editor haben ihren schon beim Anlegen, Kopien übernehmen den des
Originals (`duplicate_curriculum`); was fehlt, holt die Embedding-Nachholung — sie fasst nur
`active` an, also genau ab jetzt.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.context.curriculum_entwurf import ENTWURF
from app.db.models import ContextEdge, ContextNode, Group


def _knoten_ids(tree: dict) -> list[UUID]:
    ids = [tree["id"]]
    for kap in tree.get("kapitel", []):
        ids.append(kap["id"])
        ids += [ls["id"] for ls in kap.get("lernsequenzen", [])]
    return [UUID(str(i)) for i in ids]


def _stunden(tree: dict) -> float:
    """Wie `curriculumStd` im Frontend: Summe der Stunden der Lernsequenzen."""
    summe = 0.0
    for kap in tree.get("kapitel", []):
        for ls in kap.get("lernsequenzen", []):
            try:
                summe += float((ls.get("metadata") or {}).get("std") or 0)
            except (TypeError, ValueError):
                pass
    return summe


def _veraltet(tree: dict) -> int:
    return sum(1 for kap in tree.get("kapitel", []) for ls in kap.get("lernsequenzen", [])
               for e in ((ls.get("metadata") or {}).get("eintraege") or [])
               for feld in ("ik", "pk") for ref in (e.get(feld) or [])
               if isinstance(ref, dict) and ref.get("veraltet"))


async def _vorgaenger(db: AsyncSession, tree: dict) -> ContextNode | None:
    kennung = (tree.get("metadata") or {}).get("kopie_von")
    if not kennung:
        return None
    alt = await db.get(ContextNode, UUID(kennung))
    if alt is None or alt.content_type != "curriculum" or alt.status != "active":
        return None
    return alt


# ── Ein gültiges Curriculum je Fach, Stufe und Fassung (0.64, Jan 27.11.2026) ───────────────

class GleicheStufe(ValueError):
    """Es gibt schon ein veröffentlichtes Curriculum derselben Stufe und Fassung."""

    def __init__(self, nachricht: str, curricula: list[ContextNode]):
        super().__init__(nachricht)
        self.curricula = curricula


async def gleiche_stufe(db: AsyncSession, tree: dict) -> list[ContextNode]:
    """Veröffentlichte Curricula desselben Fachs, derselben Jahrgangsstufe und Bildungsplan-Fassung
    — ohne den Vorgänger, den der Entwurf ersetzt. Verschiedene Bänder (`metadata.band`) und
    verschiedene Fassungen zählen nicht (Jan, 27.11.2026)."""
    meta = tree.get("metadata") or {}
    stufe, fassung, band = meta.get("jahrgangsstufe"), meta.get("bp_version"), meta.get("band")
    if not stufe or tree.get("subject_id") is None:
        return []
    kandidaten = (await db.execute(sa.select(ContextNode).where(
        ContextNode.content_type == "curriculum", ContextNode.status == "active",
        ContextNode.subject_id == tree["subject_id"], ContextNode.id != UUID(str(tree["id"])),
        ContextNode.metadata_["jahrgangsstufe"].astext == str(stufe),
        ContextNode.metadata_["bp_version"].astext == str(fassung)).order_by(ContextNode.title))).scalars().all()
    vorgaenger = meta.get("kopie_von")
    return [c for c in kandidaten if str(c.id) != vorgaenger
            and not (band and (c.metadata_ or {}).get("band") and (c.metadata_ or {}).get("band") != band)]


async def _als_ersatz(db: AsyncSession, tree: dict, ersetzen: UUID, *, speichern: bool) -> dict:
    """Der Baum, als ersetzte der Entwurf `ersetzen`: `kopie_von` am Curriculum und an den
    Kapiteln gleichen Titels — wie beim YAML-Import als Ersatz. Mit `speichern` auch in der
    Datenbank (vor dem Veröffentlichen)."""
    import copy

    from sqlalchemy.orm.attributes import flag_modified

    from app.context.service import _kapitel_nach_titel, _vorbild_nehmen

    vorbilder = await _kapitel_nach_titel(db, ersetzen)
    baum = copy.deepcopy(tree)
    baum["metadata"] = {**(baum.get("metadata") or {}), "kopie_von": str(ersetzen)}
    for kap in baum.get("kapitel", []):
        km = kap.get("metadata") or {}
        if not km.get("kopie_von") and (vorbild := _vorbild_nehmen(vorbilder, kap.get("title") or "")) is not None:
            kap["metadata"] = {**km, "kopie_von": str(vorbild)}
    if speichern:
        knoten = {str(n.id): n for n in (await db.execute(sa.select(ContextNode).where(
            ContextNode.id.in_([UUID(str(tree["id"])), *[UUID(str(k["id"])) for k in tree.get("kapitel", [])]])
        ))).scalars()}
        for nid, meta in [(str(baum["id"]), baum["metadata"]), *[(str(k["id"]), k.get("metadata") or {})
                                                                   for k in baum.get("kapitel", [])]]:
            n = knoten.get(nid)
            if n is not None and (n.metadata_ or {}).get("kopie_von") != meta.get("kopie_von"):
                n.metadata_ = {**(n.metadata_ or {}), **({"kopie_von": meta["kopie_von"]} if meta.get("kopie_von") else {})}
                flag_modified(n, "metadata_")
        await db.flush()
    return baum


async def _ersatz_klaeren(db: AsyncSession, tree: dict, ersetzen: UUID | None, *, speichern: bool) -> dict:
    """Prüft die Regel „ein Curriculum je Stufe und Fassung“ und gibt den Baum zurück, mit dem
    veröffentlicht wird. `GleicheStufe`, wenn es ohne Ersatz ein zweites gäbe."""
    andere = await gleiche_stufe(db, tree)
    if not andere:
        return tree
    namen = ", ".join(f"„{c.title}“" for c in andere)
    meta = tree.get("metadata") or {}
    if meta.get("kopie_von"):
        raise GleicheStufe(f"Außer dem Curriculum, das dieser Entwurf ersetzt, gibt es für diese Stufe und "
                           f"Fassung noch {namen}. Je Stufe und Fassung gilt nur ein Curriculum — "
                           f"archiviere es zuerst oder lass den Entwurf es ersetzen.", andere)
    if ersetzen is None or ersetzen not in {c.id for c in andere}:
        raise GleicheStufe(f"Für diese Stufe und Fassung gibt es schon {namen}. Je Stufe und Fassung gilt nur "
                           f"ein Curriculum — wähle, welches der Entwurf beim Veröffentlichen ersetzt.", andere)
    return await _als_ersatz(db, tree, ersetzen, speichern=speichern)


async def _umzug(db: AsyncSession, tree: dict, vorgaenger: ContextNode) -> tuple[list, list]:
    """(umzuhängen: [(Kante, neues Kapitel)], ohne_ziel: [(Gruppe, altes Kapitel)]) — nur
    Einheiten des laufenden Schuljahrs."""
    from app.planning.calendar import load_school_year

    neu_je_alt = {(kap.get("metadata") or {}).get("kopie_von"): UUID(str(kap["id"]))
                  for kap in tree.get("kapitel", []) if (kap.get("metadata") or {}).get("kopie_von")}
    alte_kapitel = (await db.execute(
        sa.select(ContextNode).join(ContextEdge, ContextEdge.from_node_id == ContextNode.id).where(
            ContextEdge.to_node_id == vorgaenger.id, ContextEdge.relation == "part_of",
            ContextNode.content_type == "kapitel"))).scalars().all()
    if not alte_kapitel:
        return [], []
    einheit = aliased(ContextNode)
    zeilen = (await db.execute(
        sa.select(ContextEdge, Group.name)
        .join(einheit, einheit.id == ContextEdge.from_node_id)
        .outerjoin(Group, Group.id == einheit.write_scope_group_id)
        .where(ContextEdge.to_node_id.in_([k.id for k in alte_kapitel]),
               ContextEdge.relation == "references",
               einheit.content_type == "unterrichtseinheit",
               einheit.status != "deleted",
               einheit.metadata_["schuljahr"].astext == load_school_year().schuljahr))).all()
    titel = {k.id: k.title for k in alte_kapitel}
    umzug, ohne_ziel = [], []
    for kante, gruppe in zeilen:
        ziel = neu_je_alt.get(str(kante.to_node_id))
        if ziel is not None:
            umzug.append((kante, ziel))
        else:
            ohne_ziel.append({"gruppe": gruppe or "", "kapitel": titel[kante.to_node_id]})
    ohne_ziel.sort(key=lambda z: (z["gruppe"], z["kapitel"]))
    return umzug, ohne_ziel


async def uebersicht(db: AsyncSession, tree: dict, user, ersetzen: UUID | None = None) -> dict:
    """Die Übersicht vor dem Veröffentlichen — für die lesende Person (Begriffe). Mit `ersetzen`
    so, als ersetzte der Entwurf dieses Curriculum derselben Stufe (0.64)."""
    andere = await gleiche_stufe(db, tree)
    if ersetzen is not None and ersetzen in {c.id for c in andere} and not (tree.get("metadata") or {}).get("kopie_von"):
        tree = await _als_ersatz(db, tree, ersetzen, speichern=False)
    from app.context.curriculum_abdeckung import abdeckung
    from app.context.curriculum_begriffe import begriffe_aufloesen, fehlende_begriffe

    a = await abdeckung(db, tree)
    begriffe = fehlende_begriffe(tree, await begriffe_aufloesen(db, tree, user))
    aus = {
        "stunden": _stunden(tree),
        "ik": {k: a["ik"][k] for k in ("gesamt", "verknuepft", "partiell", "fehlt", "fehlt_anderswo")},
        "fremdes_fach": len(a["fremdes_fach"]),
        "veraltet": _veraltet(tree),
        "begriffe_fehlend": len(begriffe["fehlend"]),
        "begriffe_mehrdeutig": len(begriffe["mehrdeutig"]),
        # Leitlinien der Schule (0.50, AT): nur zur Information, keine Pflicht.
        "leitlinien": [{"kuerzel": l["kuerzel"], "titel": l["titel"], "aspekte": len(l["aspekte"]),
                        "vorkommend": l["vorkommend"]} for l in a["leitlinien"]],
        "vorgaenger": None,
        "einheiten_umgehaengt": 0,
        "einheiten_ohne_kapitel": [],
        # Ein Curriculum je Stufe und Fassung (0.64): die anderen veröffentlichten
        "gleiche_stufe": [{"id": c.id, "title": c.title} for c in andere],
    }
    if (alt := await _vorgaenger(db, tree)) is not None:
        umzug, ohne_ziel = await _umzug(db, tree, alt)
        aus.update(vorgaenger={"id": alt.id, "title": alt.title},
                   einheiten_umgehaengt=len(umzug), einheiten_ohne_kapitel=ohne_ziel)
    return aus


async def veroeffentlichen(db: AsyncSession, tree: dict, user, ersetzen: UUID | None = None) -> dict:
    """Veröffentlicht den Entwurf, ersetzt gegebenenfalls den Vorgänger. Kein Commit.

    Gibt es schon ein veröffentlichtes Curriculum derselben Stufe und Fassung, muss der Entwurf es
    ersetzen (`ersetzen`, sonst `GleicheStufe`, 0.64)."""
    from app.core.audit import audit

    tree = await _ersatz_klaeren(db, tree, ersetzen, speichern=True)

    ids = _knoten_ids(tree)
    await db.execute(sa.update(ContextNode).where(ContextNode.id.in_(ids), ContextNode.status == ENTWURF)
                     .values(status="active"))

    ergebnis = {"vorgaenger": None, "einheiten_umgehaengt": 0, "einheiten_ohne_kapitel": []}
    if (alt := await _vorgaenger(db, tree)) is not None:
        umzug, ohne_ziel = await _umzug(db, tree, alt)
        for kante, ziel in umzug:
            kante.to_node_id = ziel
        alter_baum = [alt.id]
        for kap_id in (await db.execute(sa.select(ContextEdge.from_node_id).where(
                ContextEdge.to_node_id == alt.id, ContextEdge.relation == "part_of"))).scalars().all():
            alter_baum.append(kap_id)
            alter_baum += (await db.execute(sa.select(ContextEdge.from_node_id).where(
                ContextEdge.to_node_id == kap_id, ContextEdge.relation == "part_of"))).scalars().all()
        await db.execute(sa.update(ContextNode).where(
            ContextNode.id.in_(alter_baum), ContextNode.status == "active",
            ContextNode.content_type.in_(("curriculum", "kapitel", "lernsequenz")),
        ).values(status="archived", archived_at=datetime.now(timezone.utc)))
        ergebnis = {"vorgaenger": {"id": alt.id, "title": alt.title},
                    "einheiten_umgehaengt": len(umzug), "einheiten_ohne_kapitel": ohne_ziel}

    await audit(db, "admin", "curriculum_published", akteur=user, ziel=("curriculum", tree["id"]),
                daten={"fach_id": tree.get("subject_id"),
                       "vorgaenger_id": str(ergebnis["vorgaenger"]["id"]) if ergebnis["vorgaenger"] else None,
                       "einheiten_umgehaengt": ergebnis["einheiten_umgehaengt"],
                       "einheiten_ohne_kapitel": len(ergebnis["einheiten_ohne_kapitel"])})
    await db.flush()
    return ergebnis
