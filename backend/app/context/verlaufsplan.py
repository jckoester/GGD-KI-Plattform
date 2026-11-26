"""Jahresverlaufspläne der Fachschaften (Päckchen BD, Schritt 4): Lesen, Rechte, Darstellung.

Ein Verlaufsplan ist ein `ContextNode` vom Typ `verlaufsplan` — je Fach (`subject_id`),
Jahrgangsstufe (`min_grade` = `max_grade`) und Schuljahr (`metadata.schuljahr`), höchstens einer
(Index `uq_context_nodes_verlaufsplan`, Alembic 0114). Seine Abschnitte stehen in
`metadata.abschnitte` als Reihenfolge und Dauer; die Daten rechnet
:mod:`app.planning.verlaufsplan_zeit` aus dem Kalender **seines** Schuljahrs
(:func:`app.planning.calendar.kalender_fuer`).

**Rechte** (BD F7, F8, F11):

- Lesen: alle Lehrkräfte und Admins. Schüler:innen bekommen die Endpunkte nicht (sie sind
  `teacher`/`admin`); der Knoten selbst ist `school` wie ein Curriculum (Jan, 25.11.2026).
- Anlegen, Bearbeiten, Beschließen, Löschen: die Fachschaft des Fachs und Admins —
  :func:`app.context.curriculum_entwurf.darf_entwurf_bearbeiten`, dieselbe Regel wie für
  Curriculum-Entwürfe. Beschließen darf jede Lehrkraft der Fachschaft (F8, Jan 25.11.2026).
- **Vergangene Schuljahre sind nur lesbar** (Archiv, F10).

Geschrieben wird nur über die Endpunkte in `verlaufsplan_router.py`. Der allgemeine PATCH-Weg
weist den Typ ab (:data:`EIGENE_WEGE`), sonst kämen Abschnitte ungeprüft in die Datenbank.
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.curriculum_entwurf import ENTWURF, darf_entwurf_bearbeiten
from app.context.curriculum_rahmen import stufen
from app.db.models import ContextEdge, ContextNode, Group, Subject
from app.planning.calendar import kalender_fuer, load_school_year
from app.planning.verlaufsplan_zeit import Planlage, lage

TYP = "verlaufsplan"
BESCHLOSSEN = "active"
#: Planungsart (Schritt 7, Jan 25.11.2026): Abschnitte nennen Lernsequenzen (Vorgabe) oder Kapitel.
SEQUENZ, KAPITEL = "sequenz", "kapitel"
PLANUNGSARTEN = (SEQUENZ, KAPITEL)
#: Feld der Abschnitte je Planungsart, und welcher Knotentyp darin steht.
BEZUGSFELD = {SEQUENZ: "sequenz_ids", KAPITEL: "kapitel_ids"}
BEZUGSTYP = {SEQUENZ: "lernsequenz", KAPITEL: "kapitel"}
#: Typen, die nur ihre eigenen Endpunkte schreiben — der allgemeine PATCH-Weg weist sie ab.
EIGENE_WEGE = frozenset({TYP})


EIGENER_WEG = "Jahresverlaufspläne bearbeitest du in ihrer eigenen Ansicht beim Fach."


def pruefe_eigener_weg(content_type: str | None) -> None:
    """422 für die allgemeinen Schreibwege (Anlegen, PATCH, Verwalten, Kopieren, Löschen):
    Abschnitte, Status und Kanten des Plans prüft nur `verlaufsplan_router.py`."""
    from fastapi import HTTPException

    if content_type in EIGENE_WEGE:
        raise HTTPException(status_code=422, detail=EIGENER_WEG)


def planungsart(plan_oder_meta) -> str:
    """Planungsart eines Plans. Pläne ohne Angabe stammen von vor Schritt 7 und nennen Kapitel."""
    meta = plan_oder_meta.metadata_ if isinstance(plan_oder_meta, ContextNode) else plan_oder_meta
    art = (meta or {}).get("planungsart")
    return art if art in PLANUNGSARTEN else KAPITEL


def aktuelles_schuljahr() -> str:
    return load_school_year().schuljahr


def ist_archiviert(plan: ContextNode) -> bool:
    """Ein Plan eines vergangenen Schuljahrs: nur noch lesbar (F10).

    „2025/26“ < „2026/27“ gilt auch als Zeichenkette — das Format ist fest (`ist_schuljahr`).
    """
    return (plan.metadata_ or {}).get("schuljahr", "") < aktuelles_schuljahr()


async def darf_bearbeiten(db: AsyncSession, plan_oder_fach, user) -> bool:
    fach = plan_oder_fach.subject_id if isinstance(plan_oder_fach, ContextNode) else plan_oder_fach
    return await darf_entwurf_bearbeiten(db, fach, user)


async def fachschaftsgruppe(db: AsyncSession, subject_id: int) -> Optional[int]:
    """Die erste Fachschaftsgruppe des Fachs — `write_scope_group_id` wie beim Import.

    Geschrieben wird trotzdem nach :func:`darf_bearbeiten` (jede Fachschaftsgruppe des Fachs);
    die Gruppe am Knoten ist nur der Pflichtwert des Scopes `subject`.
    """
    return (await db.execute(
        sa.select(Group.id).where(Group.type == "subject_department", Group.subject_id == subject_id)
        .order_by(Group.id).limit(1)
    )).scalar_one_or_none()


async def lade(db: AsyncSession, plan_id: UUID) -> Optional[ContextNode]:
    plan = await db.get(ContextNode, plan_id)
    if plan is None or plan.content_type != TYP or plan.status not in (ENTWURF, BESCHLOSSEN):
        return None
    return plan


# ── Curriculum der Stufe ──────────────────────────────────────────────────────


async def curricula_der_stufe(db: AsyncSession, subject_id: int, stufe: int) -> list[dict]:
    """Die veröffentlichten Curricula des Fachs, die diese Stufe umfassen, mit ihren Kapiteln
    samt Lernsequenzen und den Wochenstunden der Stufe (`rahmen.wochenstunden`).

    Ein Band-Curriculum (7/8) gilt für beide Stufen; seine Kapitel stehen dann in beiden Plänen
    zur Wahl, und `band` sagt es dazu (BD F6).
    """
    curricula = (await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == "curriculum", ContextNode.status == "active",
            ContextNode.subject_id == subject_id,
            sa.or_(ContextNode.min_grade.is_(None), ContextNode.min_grade <= stufe),
            sa.or_(ContextNode.max_grade.is_(None), ContextNode.max_grade >= stufe),
        ).order_by(ContextNode.title)
    )).scalars().all()
    aus = []
    for cur in curricula:
        kapitel = (await db.execute(
            sa.select(ContextNode)
            .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
            .where(ContextEdge.to_node_id == cur.id, ContextEdge.relation == "part_of",
                   ContextNode.content_type == "kapitel", ContextNode.status == "active")
            .order_by(ContextNode.metadata_["reihenfolge"].as_integer().nullslast(), ContextNode.title)
        )).scalars().all()
        sequenzen = await _sequenzen_je_kapitel(db, [k.id for k in kapitel])
        meta = cur.metadata_ or {}
        ws = ((meta.get("rahmen") or {}).get("wochenstunden") or {}).get(str(stufe))
        band = stufen(meta.get("jahrgangsstufe")) or (
            list(range(cur.min_grade, cur.max_grade + 1)) if cur.min_grade and cur.max_grade else [])
        aus.append({
            "id": str(cur.id), "titel": cur.title, "wochenstunden": ws,
            "band": len(band) > 1,
            "kapitel": [{"id": str(k.id), "titel": k.title, "std": _std((k.metadata_ or {}).get("std")),
                         "sequenzen": sequenzen.get(k.id, [])}
                        for k in kapitel],
        })
    return aus


async def _sequenzen_je_kapitel(db: AsyncSession, kapitel_ids: list[UUID]) -> dict[UUID, list[dict]]:
    """Die aktiven Lernsequenzen je Kapitel, in der Reihenfolge des Curriculums."""
    if not kapitel_ids:
        return {}
    zeilen = (await db.execute(
        sa.select(ContextEdge.to_node_id, ContextNode)
        .join(ContextNode, ContextNode.id == ContextEdge.from_node_id)
        .where(ContextEdge.to_node_id.in_(kapitel_ids), ContextEdge.relation == "part_of",
               ContextNode.content_type == "lernsequenz", ContextNode.status == "active")
        .order_by(ContextNode.metadata_["reihenfolge"].as_integer().nullslast(), ContextNode.title)
    )).all()
    aus: dict[UUID, list[dict]] = {}
    for kap_id, ls in zeilen:
        aus.setdefault(kap_id, []).append(
            {"id": str(ls.id), "titel": ls.title, "std": _std((ls.metadata_ or {}).get("std"))})
    return aus


def _std(wert) -> Optional[int]:
    try:
        return int(wert) if wert not in (None, "") else None
    except (TypeError, ValueError):
        return None


# ── Kanten auf Sequenzen oder Kapitel ─────────────────────────────────────────


async def bezugskanten_abgleichen(db: AsyncSession, plan: ContextNode) -> None:
    """`references` vom Plan auf jede genannte Sequenz bzw. jedes Kapitel — je nach Planungsart —,
    und nur auf diese (für BE und die Rückwege aus dem Curriculum). Unbekannte IDs bekommen keine
    Kante; sie bleiben im Plan stehen und erscheinen in der Bilanz als fremde Einheit."""
    art = planungsart(plan)
    feld = BEZUGSFELD[art]
    gewollt = {UUID(k) for a in (plan.metadata_ or {}).get("abschnitte", []) for k in a.get(feld) or []}
    if gewollt:
        gewollt = set((await db.execute(
            sa.select(ContextNode.id).where(ContextNode.id.in_(gewollt), ContextNode.content_type == BEZUGSTYP[art])
        )).scalars())
    vorhanden = {e.to_node_id: e for e in (await db.execute(
        sa.select(ContextEdge).where(ContextEdge.from_node_id == plan.id, ContextEdge.relation == "references")
    )).scalars()}
    for ziel, kante in vorhanden.items():
        if ziel not in gewollt:
            await db.delete(kante)
    for ziel in gewollt - vorhanden.keys():
        db.add(ContextEdge(from_node_id=plan.id, to_node_id=ziel, relation="references"))


# ── Planungsart wechseln (Schritt 7) ──────────────────────────────────────────


async def kapitel_der_sequenzen(db: AsyncSession, ids: set[str]) -> dict[str, str]:
    """Zu jeder Lernsequenz ihr Kapitel (`part_of`)."""
    if not ids:
        return {}
    zeilen = await db.execute(
        sa.select(ContextEdge.from_node_id, ContextEdge.to_node_id)
        .join(ContextNode, ContextNode.id == ContextEdge.to_node_id)
        .where(ContextEdge.from_node_id.in_([UUID(i) for i in ids]), ContextEdge.relation == "part_of",
               ContextNode.content_type == "kapitel"))
    return {str(s): str(k) for s, k in zeilen}


async def sequenzen_der_kapitel(db: AsyncSession, ids: set[str]) -> dict[str, list[str]]:
    """Zu jedem Kapitel seine aktiven Lernsequenzen, in Reihenfolge."""
    je = await _sequenzen_je_kapitel(db, [UUID(i) for i in ids])
    return {str(k): [s["id"] for s in liste] for k, liste in je.items()}


def umrechnen(abschnitte: list[dict], nach: str, *, kapitel_von: dict[str, str],
              sequenzen_von: dict[str, list[str]]) -> list[dict]:
    """Abschnitte auf die andere Planungsart umstellen (Jan, 25.11.2026: Wechsel erlaubt).

    - nach `kapitel`: jede Sequenz wird zu ihrem Kapitel, ohne Doppel — verlustfrei.
    - nach `sequenz`: jedes Kapitel wird zu allen seinen Sequenzen.

    Das Feld der alten Art bleibt stehen; es gilt nur das der Planungsart. Ein Zurückwechseln
    liest dann wieder das alte Feld nicht, sondern rechnet neu — die Abschnitte könnten sich
    seither geändert haben.
    """
    aus = []
    for a in abschnitte:
        if nach == KAPITEL:
            ids = [kapitel_von[s] for s in a.get("sequenz_ids") or [] if s in kapitel_von]
            aus.append({**a, "kapitel_ids": list(dict.fromkeys(ids))})
        else:
            ids = [s for k in a.get("kapitel_ids") or [] for s in sequenzen_von.get(k, [])]
            aus.append({**a, "sequenz_ids": list(dict.fromkeys(ids))})
    return aus


# ── Aus einem anderen Schuljahr übernehmen (Schritt 6) ────────────────────────


def _norm(t: Optional[str]) -> str:
    return (t or "").strip().casefold()


def bezuege_abbilden(abschnitte: list[dict], curricula: list[dict], art: str = KAPITEL,
                     titel_alt: Optional[dict[str, str]] = None,
                     kapitel_alt: Optional[dict[str, str]] = None) -> tuple[list[dict], int]:
    """Die Kapitel bzw. Sequenzen eines alten Plans auf die Curricula von heute legen (Schritte 6, 7).

    Was noch im veröffentlichten Curriculum der Stufe steht, bleibt. Hat das Curriculum inzwischen
    eine neue Fassung (neue Knoten), findet es sich über den **gleichen Titel** wieder — nur bei
    genau einem Treffer, sonst wäre es geraten. Der Rest fällt weg und wird gezählt, damit die
    Oberfläche es sagen kann.

    Sequenzen heißen oft gleich („Einführung“, „Wiederholung“). Deshalb zuerst unter dem
    gleichnamigen Kapitel suchen (`kapitel_alt`: Titel des alten Kapitels je Sequenz), erst dann
    im ganzen Curriculum.
    """
    feld = BEZUGSFELD[art]
    titel_alt = titel_alt or {}
    kapitel_alt = kapitel_alt or {}
    if art == SEQUENZ:
        einheiten = [(sq, k["titel"]) for c in curricula for k in c["kapitel"] for sq in k.get("sequenzen") or []]
    else:
        einheiten = [(k, None) for c in curricula for k in c["kapitel"]]
    heute = {e["id"] for e, _ in einheiten}
    nach_titel: dict[str, list[str]] = {}
    nach_kapitel_titel: dict[tuple[str, str], list[str]] = {}
    for e, kap in einheiten:
        nach_titel.setdefault(_norm(e["titel"]), []).append(e["id"])
        if kap is not None:
            nach_kapitel_titel.setdefault((_norm(kap), _norm(e["titel"])), []).append(e["id"])

    entfallen = 0
    aus = []
    for a in abschnitte:
        ids = []
        for eid in a.get(feld) or []:
            eid = str(eid)
            if eid in heute:
                ids.append(eid)
                continue
            titel = _norm(titel_alt.get(eid))
            treffer = []
            if titel and eid in kapitel_alt:
                treffer = nach_kapitel_titel.get((_norm(kapitel_alt[eid]), titel), [])
            if len(treffer) != 1 and titel:
                treffer = nach_titel.get(titel, [])
            if len(treffer) == 1:
                ids.append(treffer[0])
            else:
                entfallen += 1
        aus.append({**a, feld: list(dict.fromkeys(ids))})
    return aus, entfallen


def kapitel_abbilden(abschnitte: list[dict], curricula: list[dict],
                     titel_alt: Optional[dict[str, str]] = None) -> tuple[list[dict], int]:
    """Kapitelgenau: :func:`bezuege_abbilden` für Kapitel."""
    return bezuege_abbilden(abschnitte, curricula, KAPITEL, titel_alt)


async def knotentitel(db: AsyncSession, ids: set[str], typ: str) -> dict[str, str]:
    """Titel von Kapiteln oder Sequenzen eines alten Plans — auch archivierter, für die
    Zuordnung per Titel."""
    if not ids:
        return {}
    zeilen = await db.execute(sa.select(ContextNode.id, ContextNode.title).where(
        ContextNode.id.in_([UUID(i) for i in ids]), ContextNode.content_type == typ))
    return {str(i): t for i, t in zeilen}


async def kapiteltitel_der_sequenzen(db: AsyncSession, ids: set[str]) -> dict[str, str]:
    """Zu jeder (auch archivierten) Sequenz der Titel ihres Kapitels."""
    eltern = await kapitel_der_sequenzen(db, ids)
    titel = await knotentitel(db, set(eltern.values()), "kapitel")
    return {s: titel[k] for s, k in eltern.items() if k in titel}


# ── Darstellung ───────────────────────────────────────────────────────────────


def _lage_dict(p: Planlage) -> dict:
    return {
        "unterrichtswochen": p.unterrichtswochen, "belegt": p.belegt, "frei": p.frei,
        "ueberhang": p.ueberhang,
        "abschnitte": [{
            "id": a.id, "nr": a.nr, "wochen": a.wochen, "von_woche": a.von_woche, "bis_woche": a.bis_woche,
            "beginn": a.beginn, "ende": a.ende, "ueber_ferien": a.ueber_ferien, "vor_ferien": a.vor_ferien,
            "halbjahreswechsel": a.halbjahreswechsel, "ausserhalb": a.ausserhalb, "stunden": a.stunden,
            "lang": a.lang,
        } for a in p.abschnitte],
        "ferienabschnitte": [{"von_woche": f.von_woche, "bis_woche": f.bis_woche, "wochen": f.wochen,
                              "endet_mit": f.endet_mit} for f in p.ferienabschnitte],
        "kapitel": [{"kapitel_id": k.kapitel_id, "titel": k.titel, "soll": k.soll, "geplant": k.geplant,
                     "wochen": k.wochen,
                     "sequenzen": [{"sequenz_id": x.sequenz_id, "titel": x.titel, "soll": x.soll,
                                    "geplant": x.geplant, "wochen": x.wochen} for x in k.sequenzen]}
                    for k in p.kapitel],
        "kapitel_ohne_abschnitt": p.kapitel_ohne_abschnitt,
        "sequenzen_ohne_abschnitt": p.sequenzen_ohne_abschnitt,
        # Ablaufleiste (zweiter Durchgang)
        "wochen": [{"nr": w.index, "montag": w.montag} for w in p.wochen],
        "ferien": [{"name": m.name, "von": m.von, "bis": m.bis, "nach_woche": m.nach_woche} for m in p.ferien],
        "halbjahr_ab_woche": p.halbjahr_ab_woche,
    }


def kurz(plan: ContextNode, fach: Optional[Subject]) -> dict:
    meta = plan.metadata_ or {}
    return {
        "id": plan.id, "titel": plan.title, "subject_id": plan.subject_id,
        "fach": fach.name if fach else None, "stufe": plan.min_grade,
        "schuljahr": meta.get("schuljahr"), "status": plan.status,
        "beschlossen_am": meta.get("beschlossen_am"),
        "wochen": sum(int(a.get("wochen") or 0) for a in meta.get("abschnitte", [])),
        "planungsart": planungsart(meta),
        "archiviert": ist_archiviert(plan), "updated_at": plan.updated_at,
    }


async def voll(db: AsyncSession, plan: ContextNode, user) -> dict:
    """Der Plan mit Lage im Kalender, Curriculum der Stufe und den Rechten der Person."""
    meta = plan.metadata_ or {}
    fach = await db.get(Subject, plan.subject_id) if plan.subject_id else None
    curricula = await curricula_der_stufe(db, plan.subject_id, plan.min_grade) if plan.subject_id else []
    kapitel = [k for c in curricula for k in c["kapitel"]]
    wochenstunden = next((c["wochenstunden"] for c in curricula if c["wochenstunden"]), None)
    cfg = kalender_fuer(meta.get("schuljahr", ""))
    archiviert = ist_archiviert(plan)
    schreiben = not archiviert and await darf_bearbeiten(db, plan, user)
    return {
        **kurz(plan, fach),
        "abschnitte": meta.get("abschnitte", []),
        "curricula": curricula,
        "wochenstunden": wochenstunden,
        # Ohne Kalender des Schuljahrs nur Wochen, keine Daten
        "kalender_fehlt": cfg is None,
        "lage": _lage_dict(lage(meta.get("abschnitte", []), cfg, wochenstunden=wochenstunden, kapitel=kapitel,
                        planungsart=planungsart(meta)))
        if cfg else None,
        "darf_bearbeiten": schreiben,
        "darf_beschliessen": schreiben and plan.status == ENTWURF,
        # Übernehmen in ein späteres Schuljahr geht auch aus dem Archiv (F10, Schritt 6)
        "darf_uebernehmen": await darf_bearbeiten(db, plan, user),
        "aktuelles_schuljahr": aktuelles_schuljahr(),
    }


def heute() -> date:
    return date.today()
