"""Der Jahresverlaufsplan einer Unterrichtsgruppe (Päckchen BD Teil B, Schritt 1).

Welcher Plan zu einer Gruppe gehört (FB2, Jan 26.11.2026): der Plan ihres **Fachs** und ihrer
**Stufe** im **laufenden** Schuljahr — Entwurf oder beschlossen, auch ein Entwurf dient als
Vorlage. Die Stufe kommt aus :func:`app.groups.jahrgang.jahrgang_aus` (Festlegung, sonst die
kleinste Klasse, sonst der Name); ohne erkennbare Stufe gibt es keinen Plan, nur einen Hinweis.

Die Wahl steht bewusst in **einer** Funktion (:func:`plan_der_gruppe`): Bekommen Pläne später
Varianten (Todo, Jan 26.11.2026), wählt die Gruppe hier ihre Variante.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context import verlaufsplan as vp
from app.context.curriculum_entwurf import ENTWURF
from app.db.models import ContextEdge, ContextNode, Group, LessonSlot
from app.planning.curriculum_resolver import _group_grade

#: Warum eine Gruppe keinen Plan hat — die Oberfläche formuliert den Satz dazu.
KEIN_FACH, KEINE_STUFE, KEIN_PLAN = "kein_fach", "keine_stufe", "kein_plan"


@dataclass
class PlanDerGruppe:
    schuljahr: str
    stufe: Optional[int]
    plan: Optional[ContextNode]
    grund: Optional[str]


async def plan_der_gruppe(db: AsyncSession, group: Group) -> PlanDerGruppe:
    schuljahr = vp.aktuelles_schuljahr()
    if group.subject_id is None:
        return PlanDerGruppe(schuljahr, None, None, KEIN_FACH)
    stufe = await _group_grade(db, group)
    if stufe is None:
        return PlanDerGruppe(schuljahr, None, None, KEINE_STUFE)
    plan = (await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == vp.TYP,
            ContextNode.subject_id == group.subject_id,
            ContextNode.min_grade == stufe,
            ContextNode.metadata_["schuljahr"].as_string() == schuljahr,
            ContextNode.status.in_((ENTWURF, vp.BESCHLOSSEN)),
        ).limit(1)
    )).scalar_one_or_none()
    return PlanDerGruppe(schuljahr, stufe, plan, None if plan else KEIN_PLAN)


def wochenschluessel(montag: date) -> str:
    """ISO-Woche wie im Planer (`wochenSchluessel` in `lib/planner.js`): „2026-W38“."""
    jahr, woche, _ = montag.isocalendar()
    return f"{jahr}-W{woche:02d}"


def abschnitt_je_woche(lage: Optional[dict]) -> dict[str, int]:
    """{ISO-Woche: Index des Abschnitts} für die Wochen, die ein Abschnitt belegt.

    Der Planer zählt Kalenderwochen, der Plan Unterrichtswochen; verbunden sind beide über den
    Montag der Unterrichtswoche. Wochen hinter dem Schuljahresende haben keinen Montag und fallen
    heraus, freie Wochen ebenso. Puffer stehen drin — die Oberfläche zeigt sie als Puffer.
    """
    if not lage:
        return {}
    montag = {w["nr"]: w["montag"] for w in lage.get("wochen", [])}
    ergebnis: dict[str, int] = {}
    for i, a in enumerate(lage.get("abschnitte", [])):
        for nr in range(a["von_woche"], a["bis_woche"] + 1):
            if nr in montag:
                m = montag[nr]
                ergebnis[wochenschluessel(m if isinstance(m, date) else date.fromisoformat(m))] = i
    return ergebnis


# ── Vorschau: Einheiten aus dem Plan (Schritt 3) ──────────────────────────────

#: Wo eine aus dem Plan angelegte Einheit ihre Herkunft trägt (FB6): Plan, Abschnitt, Lauf.
HERKUNFT = "aus_verlaufsplan"


async def einheiten_des_schuljahrs(db: AsyncSession, group_id: int, schuljahr: Optional[str]) -> list[ContextNode]:
    """Die aktiven Einheiten der Gruppe in diesem Schuljahr (wie `_load_units` im Planer);
    ``None``: in allen Schuljahren."""
    bedingungen = [
        ContextNode.content_type == "unterrichtseinheit",
        ContextNode.write_scope.in_(("group", "group_teachers")),
        ContextNode.write_scope_group_id == group_id,
        ContextNode.status == "active",
    ]
    if schuljahr is not None:
        bedingungen.append(ContextNode.metadata_["schuljahr"].as_string() == schuljahr)
    return list((await db.execute(
        sa.select(ContextNode).where(*bedingungen).order_by(ContextNode.created_at)
    )).scalars().all())


async def _kapitel_der_einheiten(db: AsyncSession, ids: list) -> set[str]:
    if not ids:
        return set()
    zeilen = await db.execute(
        sa.select(ContextEdge.to_node_id)
        .join(ContextNode, ContextNode.id == ContextEdge.to_node_id)
        .where(ContextEdge.from_node_id.in_(ids), ContextEdge.relation == "references",
               ContextNode.content_type == "kapitel"))
    return {str(k) for k in zeilen.scalars()}


async def nachfolger_der_kapitel(db: AsyncSession, ids: set[str]) -> dict[str, str]:
    """Archiviertes Kapitel → sein veröffentlichter Nachfolger über `metadata.kopie_von`, auch über
    mehrere Fassungen. Beim Veröffentlichen einer Kopie ziehen die Einheiten genau dorthin um
    (`curriculum_veroeffentlichen`); der Plan nennt aber weiter das alte Kapitel."""
    ergebnis: dict[str, str] = {}
    offen = {i: i for i in ids}   # aktuell gesuchter Vorgänger → Ausgangskapitel
    for _ in range(5):            # mehr Fassungen in einem Schuljahr gibt es nicht
        if not offen:
            break
        zeilen = (await db.execute(sa.select(ContextNode.id, ContextNode.status, ContextNode.metadata_["kopie_von"].as_string())
                                   .where(ContextNode.content_type == "kapitel",
                                          ContextNode.metadata_["kopie_von"].as_string().in_(list(offen))))).all()
        weiter = {}
        for kid, status, vorgaenger in zeilen:
            start = offen.get(vorgaenger)
            if start is None or start in ergebnis:
                continue
            if status == "active":
                ergebnis[start] = str(kid)
            else:
                weiter[str(kid)] = start
        offen = weiter
    return ergebnis


async def vorschlaege(db: AsyncSession, group: Group, plan: ContextNode, lage: Optional[dict]):
    """Die Vorschläge für den Plan dieser Gruppe — Datenbankteil zu
    :func:`app.planning.verlaufsplan_vorlage.vorschau`. Ohne Lage (kein Kalender) keine."""
    from app.planning.verlaufsplan_vorlage import vorschau

    if not lage:
        return []
    meta = plan.metadata_ or {}
    abschnitte = meta.get("abschnitte", [])
    art = vp.planungsart(meta)
    seq_ids = {str(x) for a in abschnitte for x in a.get("sequenz_ids") or []}
    kap_ids = {str(x) for a in abschnitte for x in a.get("kapitel_ids") or []}
    kapitel_von = await vp.kapitel_der_sequenzen(db, seq_ids) if art == vp.SEQUENZ else {}
    alle_kapitel = kap_ids | set(kapitel_von.values())
    aktiv = set()
    if alle_kapitel:
        aktiv = {str(i) for i in (await db.execute(sa.select(ContextNode.id).where(
            ContextNode.id.in_([UUID(i) for i in alle_kapitel]),
            ContextNode.content_type == "kapitel", ContextNode.status == "active"))).scalars()}
    nachfolger = await nachfolger_der_kapitel(db, alle_kapitel - aktiv)
    titel = {**await vp.knotentitel(db, seq_ids, "lernsequenz"),
             **await vp.knotentitel(db, alle_kapitel | set(nachfolger.values()), "kapitel")}

    einheiten = await einheiten_des_schuljahrs(db, group.id, meta.get("schuljahr", ""))

    def herkunft(e) -> dict:
        h = (e.metadata_ or {}).get(HERKUNFT)
        return h if isinstance(h, dict) else {}

    # Aus diesem Plan und einem Abschnitt, den es noch gibt: zählen nur über ihren Abschnitt, nicht
    # über das Kapitel (FB3 vor FB5). Die eines gelöschten Abschnitts zählen wie jede andere Einheit.
    noch_da = {str(a["id"]) for a in abschnitte if a.get("id")}
    aus_plan = [e for e in einheiten if herkunft(e).get("plan_id") == str(plan.id)
                and str(herkunft(e).get("abschnitt_id")) in noch_da]
    angelegt = {str(herkunft(e)["abschnitt_id"]) for e in aus_plan if herkunft(e).get("abschnitt_id")}
    andere = [e for e in einheiten if e not in aus_plan]
    # `populate_existing`: Die Sitzung läuft mit `expire_on_commit=False`; ohne das gäbe ein zweiter
    # Aufruf (nach der Sperre in :func:`anlegen`) die Termine im Stand des ersten zurück.
    slots = (await db.execute(sa.select(LessonSlot).where(LessonSlot.group_id == group.id)
                              .execution_options(populate_existing=True))).scalars().all()
    return vorschau(
        abschnitte, lage, planungsart=art, kapitel_von=kapitel_von, titel=titel, kapitel_aktiv=aktiv,
        slots=slots, kapitel_mit_einheit=await _kapitel_der_einheiten(db, [e.id for e in andere]),
        angelegte_abschnitte=angelegt, heute=vp.heute(), nachfolger=nachfolger,
    )


# ── Anlegen und Rückgängig (Schritt 4) ─────────────────────────────────────────

#: Farben der Einheiten (`UE_PALETTE` in `lib/planner.js`); die Farbe folgt dem Kapitel wie im Plan.
FARBEN = 8
SNAPSHOT_LABEL = "Vor: Einheiten aus dem Jahresverlaufsplan"


def farbe_des_kapitels(kapitel_id: Optional[str], curricula: list[dict]) -> Optional[int]:
    """Index des Kapitels in der Reihenfolge der Curricula der Stufe — dieselbe Farbe wie der Block in
    der Ablaufleiste (`abschnittFarbe`). Ohne Kapitel keine Angabe (der Planer nimmt dann die erste)."""
    reihenfolge = [k["id"] for c in curricula for k in c.get("kapitel", [])]
    return reihenfolge.index(kapitel_id) % FARBEN if kapitel_id in reihenfolge else None


def vorschlag_dict(v, curricula: list[dict]) -> dict:
    """Ein Vorschlag als JSON — dieselbe Form für den Dialog im Planer und den Assistenten (0.61)."""
    return {
        "index": v.index, "nr": v.nr, "abschnitt_id": v.abschnitt_id, "titel": v.titel, "wochen": v.wochen,
        "anlegen": v.anlegen, "grund": v.grund, "kapitel_id": v.kapitel_id, "kapitel_titel": v.kapitel_titel,
        "kapitel_fehlt": v.kapitel_fehlt, "beschreibung": v.beschreibung, "stunden": v.stunden, "belegt": v.belegt,
        "ohne_termine": v.ohne_termine, "farbe": farbe_des_kapitels(v.kapitel_id, curricula),
    }


#: Höchstlänge eines eigenen Titels (wie `UnitCreate`/Abschnitt im Plan)
TITEL_MAX = 200


def _anpassen(liste: list, auslassen, titel) -> list:
    """Wünsche der Lehrkraft aus dem Chat (0.61, F1a): Abschnitte weglassen, Titel ändern — nach der
    Nummer `nr` der Vorschau. Termine, Kapitel und Regeln bleiben beim Server."""
    weg = {int(n) for n in auslassen or []}
    neu = {int(n): str(t).strip()[:TITEL_MAX] for n, t in (titel or {}).items() if str(t).strip()}
    aus = [v for v in liste if v.nr not in weg]
    for v in aus:
        if v.nr in neu:
            v.titel = neu[v.nr]
    return aus


async def anlegen(db: AsyncSession, group: Group, plan: ContextNode, voll: dict, user, *,
                  auslassen=None, titel: Optional[dict] = None) -> dict:
    """Legt je Vorschlag mit `anlegen` eine Einheit an und belegt ihre Termine (FB3–FB6).

    Vorher ein Snapshot (Verlauf des Planers, wie bei jeder Änderung); dann alles in **einer**
    Transaktion. Jede Einheit trägt `metadata.aus_verlaufsplan` = Plan, Abschnitt und Lauf — daran
    erkennt die Vorschau, was schon angelegt ist, und :func:`rueckgaengig`, was zum Lauf gehört.

    `auslassen` (Nummern) und `titel` ({Nummer: Titel}) nutzt nur der Assistent (0.61, F1a); der
    Knopf im Planer legt alles an. Die Nummern sind die `nr` der Vorschau.
    """
    from datetime import datetime, timezone
    from uuid import uuid4

    from app.planning.service import create_unit_node
    from app.planning.snapshots import create_snapshot

    nichts = {"lauf_id": None, "einheiten": 0, "stunden": 0, "angelegt": []}
    if not _anpassen([v for v in await vorschlaege(db, group, plan, voll["lage"]) if v.anlegen], auslassen, titel):
        return nichts
    # `create_snapshot` committet selbst. Danach die Gruppe sperren und **neu** rechnen: Ein zweiter
    # Aufruf (Doppelklick) wartet hier, bis der erste committet hat, und findet dann seine Einheiten
    # als `schon_angelegt` — sonst entstünde alles doppelt.
    snapshot = await create_snapshot(db, group.id, reason="edit", label=SNAPSHOT_LABEL, created_by=user.sub)
    await db.execute(sa.select(Group.id).where(Group.id == group.id).with_for_update())
    liste = _anpassen([v for v in await vorschlaege(db, group, plan, voll["lage"]) if v.anlegen], auslassen, titel)
    if not liste:
        return nichts
    lauf = uuid4().hex
    jetzt = datetime.now(timezone.utc)
    stunden = 0
    angelegt = []
    for v in liste:
        ue = await create_unit_node(
            db, group.id, group.subject_id, user, v.titel,
            farbe=farbe_des_kapitels(v.kapitel_id, voll["curricula"]),
            kapitel_node_id=UUID(v.kapitel_id) if v.kapitel_id else None, commit=False,
        )
        ue.content = v.beschreibung
        # Das Schuljahr des Plans — `create_unit_node` nimmt das der Konfiguration; beide sind gleich
        # (`plan_der_gruppe` wählt den Plan des laufenden), so steht es aber fest.
        ue.metadata_ = {**(ue.metadata_ or {}), "schuljahr": (plan.metadata_ or {}).get("schuljahr"), HERKUNFT: {
            "plan_id": str(plan.id), "abschnitt_id": v.abschnitt_id, "lauf_id": lauf,
            "snapshot_id": str(snapshot.id),
        }}
        # Nur belegen, was in der Datenbank noch frei ist (FB4) — die Planer-Routen sperren die Gruppe
        # nicht. Ohne Stunde am Termin gibt es keinen Entwurf einzuordnen (`ordne_entwurf_ein`).
        if v.slot_ids:
            getroffen = (await db.execute(
                sa.update(LessonSlot)
                .where(LessonSlot.id.in_(v.slot_ids), LessonSlot.group_id == group.id,
                       LessonSlot.kategorie == "unterricht", LessonSlot.ue_node_id.is_(None),
                       LessonSlot.stunde_node_id.is_(None), sa.not_(LessonSlot.pinned))
                .values(ue_node_id=ue.id, updated_at=jetzt)
                .returning(LessonSlot.id)
                .execution_options(synchronize_session=False)
            )).scalars().all()
            stunden += len(getroffen)
        else:
            getroffen = []
        angelegt.append({"nr": v.nr, "titel": v.titel, "kapitel": v.kapitel_titel, "stunden": len(getroffen)})
    await db.commit()
    return {"lauf_id": lauf, "einheiten": len(liste), "stunden": stunden, "angelegt": angelegt}


class NichtMehrRueckgaengig(Exception):
    """Eine Einheit des Laufs hat schon Stunden — Rückgängig löschte fremde Arbeit mit."""


async def rueckgaengig(db: AsyncSession, group: Group, lauf_id: str) -> int:
    """Löscht genau die Einheiten eines Laufs (FB6). Ihre Termine werden dabei wieder frei
    (`lesson_slots.ue_node_id` ON DELETE SET NULL); sonst ändert sich am Plan nichts.

    Bewusst **ohne** Snapshot-Restore: Der stellte auch alles zurück, was seit dem Anlegen sonst
    geändert wurde. Der Lauf hat nur Einheiten angelegt und freie Termine belegt — beides nimmt das
    Löschen genau zurück. Der Snapshot davor bleibt im Verlauf des Planers.

    Gibt die Zahl der gelöschten Einheiten zurück; :class:`NichtMehrRueckgaengig`, wenn eine schon
    eine Stunde hat (am Termin oder als Entwurf in der Einheit).
    """
    einheiten = [e for e in await einheiten_des_schuljahrs(db, group.id, None)
                 if isinstance(h := (e.metadata_ or {}).get(HERKUNFT), dict) and h.get("lauf_id") == lauf_id]
    if not einheiten:
        return 0
    ids = [e.id for e in einheiten]
    mit_stunde = (await db.execute(sa.select(sa.func.count()).select_from(LessonSlot).where(
        LessonSlot.ue_node_id.in_(ids), LessonSlot.stunde_node_id.is_not(None)))).scalar_one()
    entwuerfe = (await db.execute(
        sa.select(sa.func.count()).select_from(ContextEdge)
        .join(ContextNode, ContextNode.id == ContextEdge.from_node_id)
        .where(ContextEdge.to_node_id.in_(ids), ContextEdge.relation == "part_of",
               ContextNode.content_type == "unterrichtsstunde"))).scalar_one()
    if mit_stunde or entwuerfe:
        raise NichtMehrRueckgaengig()
    for e in einheiten:
        await db.delete(e)
    await db.commit()
    return len(einheiten)
