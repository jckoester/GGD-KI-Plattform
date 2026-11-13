"""Stunden und Einheiten als Vorlage kopieren (0.42, Päckchen AO).

Eine Kopie ist ein **neuer Entwurf in einer aktuellen Gruppe desselben Fachs** (F5): Er gehört
der kopierenden Person, liegt in einer Einheit der Zielgruppe (F6) und vermerkt seine Herkunft
in ``metadata.kopie_von`` (F9). Kopieren darf, wer die Quelle lesen darf
(``zugang_zur_stunde``) — auch aus dem Archiv (F11).

**Was mitkommt** (Feldliste aus Schritt 0, Plan 0.42):

- Titel, Stundenziel, Phasen mit ihren Schemafeldern — Name, Dauer, Beschreibung, Prio,
  Methode, Sozialform, Material. Jede Phase bekommt eine **neue Kennung**; was Nachbereitung,
  Kürzen und Übertragen an eine Phase schreiben (``status``, ``kuerzung``, ``uebertrag_von`` …),
  gehört zur gehaltenen Stunde und bleibt dort. Das ist dieselbe Grenze wie
  ``uebernimm_zusatzfelder``: Schemafelder ja, alles andere nein.
- Kompetenzen (``refs`` Typ ``ik``/``pk``) in der **Fassung der Zielgruppe** (F4 a): Gilt dort
  eine andere Bildungsplan-Fassung, wird der Verweis auf den Zwilling umgestellt — gleiche
  Nummer, Text weitgehend gleich, dieselbe Regel wie beim Curriculum-Relinking
  (``app/context/relink.py``). Gibt es keinen, fällt der Verweis weg und wird gemeldet.
- Begriffe (``refs`` Typ ``concept``) und Material, soweit die Zielgruppe sie lesen kann —
  sonst weg und gemeldet. Methoden und Sozialformen sind schulweit und kommen immer mit.
- Die Nachbereitungsnotiz als ``notiz_aus_vorlage`` (S1), **nicht** als ``reflexion``: Sie
  steht im neuen Entwurf als Hinweis, zählt aber nicht als Nachbereitung und nicht im Vektor.

**Was nicht mitkommt:** Termin, Nachbereitungsstand, Kürzungen und Übertrag
(``refs_offen``), verworfene und vorgeschlagene Begriffe, Chat-Bezug (``assistant_id``).

**Einheit** (Schritt 4): neue Einheit am Jahresplan der Zielgruppe, laufendes Schuljahr, Titel,
Beschreibung, Farbe; Kapitelverweise nur, wenn das Kapitel in einem Curriculum der Zielgruppe
liegt (S2); alle lesbaren Stunden in Reihenfolge, ohne Termine.

Die Funktionen hier **committen nicht** — das tut die Route. Eine Einheit entsteht damit ganz
oder gar nicht: Scheitert eine Stunde, rollt die Sitzung alles zurück.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import JwtPayload
from app.context.editions import aktive_bp_version
from app.context.relink import _decide, _twin_map
from app.context.visibility import OFFENE_SCOPES
from app.db.models import ContextEdge, ContextNode, Group, LessonSlot
from app.groups.aktualitaet import gruppe_ist_aktuell
from app.planning.curriculum_resolver import group_grade
from app.planning.permissions import require_group_teacher
from app.planning.schemas import LessonPhaseItem
from app.planning.zuordnung import gehoert_zur_gruppe

#: Lesbare Zustände einer Quelle (F11) — archivierte Stunden lassen sich kopieren.
LESBAR = ("active", "archived")

_KOMPETENZ_TYPEN = {"ik": "ik_kompetenz", "pk": "pk_kompetenz"}
_GRUPPEN_SCOPES = ("group", "group_teachers")


@dataclass
class Meldung:
    """Was an der Kopie anders ist als an der Quelle."""

    art: str    # "kompetenz" | "begriff" | "material" | "kapitel"
    titel: str
    was: str    # "weggelassen" | "umgestellt"
    grund: str
    phase: str | None = None
    stunde: str | None = None   # bei der Einheiten-Kopie: in welcher Stunde


@dataclass
class Ziel:
    """Die Zielgruppe einer Kopie samt allem, was sich je Gruppe nur einmal zu ermitteln lohnt."""

    gruppe: Group
    user: JwtPayload
    jahrgang: int | None
    _fassung: dict[tuple[int, str], str | None] = field(default_factory=dict)
    _zwillinge: dict[tuple[int, str, str], dict[str, ContextNode]] = field(default_factory=dict)


async def pruefe_ziel(db: AsyncSession, group_id: int, fach_id: int | None, user: JwtPayload) -> Ziel:
    """Zielgruppe prüfen: Lehrkraft dort (403), laufendes Schuljahr und dasselbe Fach (422)."""
    gruppe = await require_group_teacher(group_id, user, db)
    if not await gruppe_ist_aktuell(db, gruppe):
        raise HTTPException(
            status_code=422, detail="Kopieren geht nur in eine Gruppe des laufenden Schuljahres.")
    if fach_id is None or gruppe.subject_id != fach_id:
        raise HTTPException(status_code=422, detail="Kopieren geht nur in eine Gruppe desselben Fachs.")
    return Ziel(gruppe=gruppe, user=user, jahrgang=await group_grade(db, gruppe.id))


async def zieleinheit(
    db: AsyncSession, ziel: Ziel, einheit_id: UUID | None, neue_einheit: str | None
) -> ContextNode:
    """Die Einheit, in die kopiert wird — eine bestehende der Zielgruppe oder eine neue (F6)."""
    from app.planning.service import create_unit_node

    if (einheit_id is None) == (not (neue_einheit or "").strip()):
        raise HTTPException(
            status_code=422, detail="Gib genau eins an: eine Einheit der Gruppe oder den Titel einer neuen.")
    if einheit_id is not None:
        einheit = await db.get(ContextNode, einheit_id)
        if (einheit is None or einheit.content_type != "unterrichtseinheit"
                or not gehoert_zur_gruppe(einheit, ziel.gruppe.id)):
            raise HTTPException(status_code=422, detail="Diese Einheit gehört nicht zur Zielgruppe.")
        return einheit
    return await create_unit_node(
        db, ziel.gruppe.id, ziel.gruppe.subject_id, ziel.user, neue_einheit.strip(), commit=False)


# ── Lesbarkeit und Fassung ────────────────────────────────────────────────────


def _fuer_ziel_lesbar(node: ContextNode, ziel: Ziel) -> bool:
    """Ist ein verwiesener Baustein in der Zielgruppe zu sehen?

    Schulweit Freigegebenes immer; was an einer Gruppe hängt, nur, wenn es die Zielgruppe ist;
    Privates nur, wenn es der kopierenden Person gehört. Ein Arbeitsblatt, das nur für die alte
    Gruppe freigegeben war, bleibt also draußen — die Lehrkraft entscheidet am Baustein, ob
    sie es auch für die neue freigibt (Plan F4).
    """
    if node.status != "active":
        return False
    if node.read_scope in OFFENE_SCOPES:
        return True
    if node.read_scope in _GRUPPEN_SCOPES:
        return node.read_scope_group_id == ziel.gruppe.id
    return node.read_scope == "private" and node.owner_pseudonym == ziel.user.sub


async def _geltende_fassung(db: AsyncSession, ziel: Ziel, fach_id: int, typ: str) -> str | None:
    """Die in der Zielgruppe geltende Fassung je Fach und Bausteinart (wie die Suche)."""
    schluessel = (fach_id, typ)
    if schluessel not in ziel._fassung:
        verfuegbar = set((await db.execute(
            sa.select(ContextNode.bp_version).where(
                ContextNode.subject_id == fach_id,
                ContextNode.content_type == typ,
                ContextNode.status == "active",
                ContextNode.bp_version != "",
            ).distinct()
        )).scalars())
        ziel._fassung[schluessel] = (
            aktive_bp_version(ziel.jahrgang, verfuegbar) if ziel.jahrgang is not None and verfuegbar
            else None)
    return ziel._fassung[schluessel]


def _nummer(node: ContextNode) -> str:
    md = node.metadata_ or {}
    return str(md.get("kompetenz_nr") or md.get("nr") or md.get("pk_id") or "")


async def _kompetenz_fuer_ziel(
    db: AsyncSession, ziel: Ziel, node: ContextNode
) -> tuple[ContextNode | None, str | None]:
    """→ (Knoten für die Kopie, Grund). ``None`` als Knoten heißt: weglassen.

    Gilt in der Zielgruppe dieselbe Fassung — oder lässt sie sich nicht bestimmen (Kursstufe,
    unversionierter Knoten) —, bleibt der Verweis. Sonst zählt der Zwilling in der geltenden
    Fassung, wenn es ihn gibt und sein Text nicht inhaltlich geändert ist.
    """
    if not node.bp_version or node.subject_id is None:
        return node, None
    gilt = await _geltende_fassung(db, ziel, node.subject_id, node.content_type)
    if gilt is None or gilt == node.bp_version:
        return node, None
    schluessel = (node.subject_id, node.content_type, gilt)
    if schluessel not in ziel._zwillinge:
        ziel._zwillinge[schluessel] = await _twin_map(
            db, node.subject_id, node.content_type, "kompetenz_nr", gilt)
    nr = _nummer(node)
    entscheidung = _decide(
        {"node_id": node.id, "title": node.title}, ziel._zwillinge[schluessel].get(nr), nr)
    if entscheidung["decision"] == "relink":
        return ziel._zwillinge[schluessel][nr], None
    if entscheidung["new_node_id"] is None:
        return None, "In der Fassung des Bildungsplans, die für die Gruppe gilt, gibt es sie nicht."
    return None, "In der Fassung des Bildungsplans, die für die Gruppe gilt, lautet sie anders."


# ── Stunde ────────────────────────────────────────────────────────────────────


async def _knoten(db: AsyncSession, ids: set[UUID]) -> dict[UUID, ContextNode]:
    if not ids:
        return {}
    zeilen = await db.execute(sa.select(ContextNode).where(ContextNode.id.in_(ids)))
    return {n.id: n for n in zeilen.scalars()}


def _uuid(wert: Any) -> UUID | None:
    try:
        return UUID(str(wert)) if wert else None
    except ValueError:
        return None


async def _refs_fuer_ziel(
    db: AsyncSession, ziel: Ziel, refs: list[dict], meldungen: list[Meldung]
) -> list[dict]:
    knoten = await _knoten(db, {i for r in refs if (i := _uuid(r.get("node_id")))})
    ergebnis: list[dict] = []
    gesehen: set[str] = set()
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        typ = ref.get("typ")
        art = "kompetenz" if typ in _KOMPETENZ_TYPEN else "begriff"
        titel = ref.get("titel") or ref.get("code") or ""
        node = knoten.get(_uuid(ref.get("node_id")))
        if node is None or not _fuer_ziel_lesbar(node, ziel):
            meldungen.append(Meldung(art, titel, "weggelassen", "Für die Gruppe nicht sichtbar."))
            continue
        neu = dict(ref)
        if typ in _KOMPETENZ_TYPEN:
            ersatz, grund = await _kompetenz_fuer_ziel(db, ziel, node)
            if ersatz is None:
                meldungen.append(Meldung(art, titel, "weggelassen", grund))
                continue
            if ersatz.id != node.id:
                neu.update(node_id=str(ersatz.id), code=_nummer(ersatz) or ref.get("code"),
                           titel=ersatz.title)
                meldungen.append(Meldung(
                    art, titel, "umgestellt", "Auf die Fassung des Bildungsplans umgestellt, "
                    "die für die Gruppe gilt."))
        if neu["node_id"] in gesehen:
            continue
        gesehen.add(neu["node_id"])
        ergebnis.append(neu)
    return ergebnis


async def _phasen_fuer_ziel(
    db: AsyncSession, ziel: Ziel, phasen: list[dict], meldungen: list[Meldung]
) -> list[dict]:
    """Phasen mit ihren Schemafeldern, neuen Kennungen und lesbarem Material."""
    import uuid

    schema = set(LessonPhaseItem.model_fields)
    material_ids = {
        i
        for p in phasen if isinstance(p, dict)
        for m in p.get("material") or [] if isinstance(m, dict) and m.get("typ") == "node"
        if (i := _uuid(m.get("node_id")))
    }
    knoten = await _knoten(db, material_ids)
    ergebnis: list[dict] = []
    for phase in phasen:
        if not isinstance(phase, dict):
            continue
        neu = {k: v for k, v in phase.items() if k in schema}
        neu["id"] = str(uuid.uuid4())
        material = []
        for m in phase.get("material") or []:
            if not isinstance(m, dict):
                continue
            if m.get("typ") == "node":
                node = knoten.get(_uuid(m.get("node_id")))
                if node is None or not _fuer_ziel_lesbar(node, ziel):
                    meldungen.append(Meldung(
                        "material", m.get("titel") or "Baustein", "weggelassen",
                        "Für die Gruppe nicht freigegeben.", phase=phase.get("name")))
                    continue
            material.append(m)
        neu["material"] = material
        ergebnis.append(neu)
    return ergebnis


async def _notiz_aus_vorlage(db: AsyncSession, quelle: ContextNode) -> dict | None:
    """Die Nachbereitungsnotiz der Quelle als Hinweis für die Kopie (S1).

    ``reflexion`` der Quelle samt deren Termin; hat sie keine und ist selbst eine Kopie, die
    Notiz, die sie mitbekommen hat — unverändert, denn deren Herkunft ist die richtige.
    """
    md = quelle.metadata_ or {}
    text = (md.get("reflexion") or "").strip() if isinstance(md.get("reflexion"), str) else ""
    if text:
        datum = (await db.execute(
            sa.select(LessonSlot.date).where(LessonSlot.stunde_node_id == quelle.id)
        )).scalar_one_or_none()
        return {"text": text, "kopie_von": str(quelle.id),
                "datum": datum.isoformat() if datum else None}
    geerbt = md.get("notiz_aus_vorlage")
    if isinstance(geerbt, dict) and (geerbt.get("text") or "").strip():
        return dict(geerbt)
    return None


async def _letzte_stunde(db: AsyncSession, einheit_id: UUID) -> ContextNode | None:
    """Wie ``create_lesson``: Die jüngste aktive Stunde der Einheit wird Vorgängerin."""
    return (await db.execute(
        sa.select(ContextNode)
        .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
        .where(
            ContextEdge.to_node_id == einheit_id,
            ContextEdge.relation == "part_of",
            ContextNode.content_type == "unterrichtsstunde",
            ContextNode.status == "active",
        )
        .order_by(ContextNode.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()


async def kopiere_stunde(
    db: AsyncSession, quelle: ContextNode, ziel: Ziel, einheit: ContextNode,
    meldungen: list[Meldung],
    vorgaenger: ContextNode | None | bool = True,
) -> ContextNode:
    """Legt die Kopie an (ohne Commit) und hängt sie ans Ende der Einheit.

    ``vorgaenger=True`` sucht die letzte Stunde der Einheit; die Einheiten-Kopie reicht die
    zuvor kopierte Stunde (oder ``None``) selbst durch, weil die neuen dieselbe Zeit tragen.
    """
    from app.planning.material_edges import synchronisiere_materialkanten

    md = quelle.metadata_ or {}
    meta: dict[str, Any] = {
        "phasen": await _phasen_fuer_ziel(db, ziel, md.get("phasen") or [], meldungen),
        "kopie_von": str(quelle.id),
    }
    if md.get("stundenziel"):
        meta["stundenziel"] = md["stundenziel"]
    refs = await _refs_fuer_ziel(db, ziel, md.get("refs") or [], meldungen)
    if refs:
        meta["refs"] = refs
    notiz = await _notiz_aus_vorlage(db, quelle)
    if notiz:
        meta["notiz_aus_vorlage"] = notiz

    if vorgaenger is True:
        vorgaenger = await _letzte_stunde(db, einheit.id)
    gruppe_id = ziel.gruppe.id
    stunde = ContextNode(
        category="artifact",
        content_type="unterrichtsstunde",
        title=quelle.title,
        title_locked=quelle.title_locked,
        niveau=quelle.niveau,
        bp_version=quelle.bp_version,
        read_scope="group_teachers",
        write_scope="group_teachers",
        read_scope_group_id=gruppe_id,
        write_scope_group_id=gruppe_id,
        owner_pseudonym=ziel.user.sub,
        subject_id=ziel.gruppe.subject_id,
        metadata_=meta,
        status="active",
    )
    db.add(stunde)
    await db.flush()

    db.add(ContextEdge(from_node_id=stunde.id, to_node_id=einheit.id, relation="part_of", metadata_={}))
    if vorgaenger:
        db.add(ContextEdge(
            from_node_id=stunde.id, to_node_id=vorgaenger.id, relation="follows", metadata_={}))
    await synchronisiere_materialkanten(db, stunde.id, meta)
    await db.flush()
    return stunde


# ── Einheit (Schritt 4) ───────────────────────────────────────────────────────


async def lesbare_stunden_der_einheit(
    db: AsyncSession, einheit: ContextNode, user: JwtPayload
) -> list[ContextNode]:
    """Die Stunden der Einheit, die diese Person lesen darf, in Reihenfolge (`follows`).

    Lehrkraft der Gruppe: alle. Sonst nur eigene — wie im Archiv (F12, Fall 4b). Gelöschte nie,
    archivierte schon (F11).
    """
    from app.planning.archiv import _ordne
    from app.planning.permissions import ist_gruppenlehrkraft

    abfrage = (
        sa.select(ContextNode)
        .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
        .where(
            ContextEdge.to_node_id == einheit.id,
            ContextEdge.relation == "part_of",
            ContextNode.content_type == "unterrichtsstunde",
            ContextNode.status.in_(LESBAR),
        )
    )
    gruppe_id = einheit.write_scope_group_id
    if gruppe_id is None or not await ist_gruppenlehrkraft(gruppe_id, user, db):
        abfrage = abfrage.where(ContextNode.owner_pseudonym == user.sub)
    stunden = {n.id: n for n in (await db.execute(abfrage)).scalars()}
    folgt: dict[UUID, UUID] = {}
    if stunden:
        folgt = dict((await db.execute(
            sa.select(ContextEdge.from_node_id, ContextEdge.to_node_id).where(
                ContextEdge.from_node_id.in_(list(stunden)), ContextEdge.relation == "follows")
        )).all())
    return [stunden[i] for i in _ordne(stunden, folgt)]


async def _kapitel_fuer_ziel(
    db: AsyncSession, ziel: Ziel, quelle: ContextNode, meldungen: list[Meldung]
) -> list[UUID]:
    """Kapitelverweise der Quelle, die in einem Curriculum der Zielgruppe liegen (S2)."""
    from app.planning.curriculum_resolver import resolve_group_curricula

    kapitel = (await db.execute(
        sa.select(ContextNode)
        .join(ContextEdge, ContextEdge.to_node_id == ContextNode.id)
        .where(
            ContextEdge.from_node_id == quelle.id,
            ContextEdge.relation == "references",
            ContextNode.content_type == "kapitel",
        )
    )).scalars().all()
    if not kapitel:
        return []
    erlaubt = {
        k.id for cur in (await resolve_group_curricula(db, ziel.gruppe.id)).curricula for k in cur.kapitel
    }
    behalten = []
    for k in kapitel:
        if k.id in erlaubt:
            behalten.append(k.id)
        else:
            meldungen.append(Meldung(
                "kapitel", k.title, "weggelassen", "Gehört zu keinem Curriculum der Gruppe."))
    return behalten


async def kopiere_einheit(
    db: AsyncSession, quelle: ContextNode, stunden: list[ContextNode], ziel: Ziel,
    meldungen: list[Meldung],
) -> tuple[ContextNode, list[ContextNode]]:
    """Legt die Einheit samt Stunden in der Zielgruppe an (ohne Commit, ohne Termine).

    Die neue Einheit hängt am Jahresplan der Zielgruppe im laufenden Schuljahr, trägt Titel,
    Beschreibung und Farbe der Quelle und die Kapitel, die dort passen. Die Stunden folgen
    einander in der Reihenfolge der Quelle — über ``vorgaenger`` durchgereicht, weil alle
    in derselben Transaktion entstehen und dieselbe Anlegezeit tragen.
    """
    from app.planning.service import create_unit_node

    md = quelle.metadata_ or {}
    einheit = await create_unit_node(
        db, ziel.gruppe.id, ziel.gruppe.subject_id, ziel.user, quelle.title,
        farbe=md.get("farbe"), commit=False)
    if quelle.content:
        einheit.content = quelle.content
    einheit.metadata_ = {**(einheit.metadata_ or {}), "kopie_von": str(quelle.id)}
    for kapitel_id in await _kapitel_fuer_ziel(db, ziel, quelle, meldungen):
        db.add(ContextEdge(
            from_node_id=einheit.id, to_node_id=kapitel_id, relation="references", metadata_={}))

    neue: list[ContextNode] = []
    vorgaenger: ContextNode | None = None
    for stunde in stunden:
        eigene: list[Meldung] = []
        vorgaenger = await kopiere_stunde(db, stunde, ziel, einheit, eigene, vorgaenger=vorgaenger)
        for m in eigene:
            m.stunde = stunde.title
        meldungen.extend(eigene)
        neue.append(vorgaenger)
    await db.flush()
    return einheit, neue


def meldungen_als_dicts(meldungen: list[Meldung]) -> list[dict]:
    return [m.__dict__.copy() for m in meldungen]
