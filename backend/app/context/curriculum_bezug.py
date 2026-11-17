"""Der Curriculumbezug einer Konversation (0.46, Päckchen AP Teil B, Schritt 6).

`conversations.curriculum_node_id` — das Curriculum, an dem der Curriculum-Assistent arbeitet.
Gesetzt beim Anlegen aus dem Editor („Mit dem Assistenten bearbeiten") oder im Gespräch über
`waehle_curriculum` / `lege_curriculum_an`. Die Funktionen nehmen ihn als Vorgabe; der Assistent
bekommt ihn als Systemzeile; der Kopf des Chats verlinkt ihn.

Wie beim Stundenbezug (`app/planning/stundenbezug.py`) gilt beim Setzen und bei jedem Lesen
dieselbe Regel wie im Editor (`zugang`, Teil A) — was einmal erlaubt war, ist es nicht für immer.
"""
from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.curriculum_assistent import zugang
from app.context.curriculum_entwurf import ENTWURF
from app.db.models import ContextNode, Conversation, Subject


async def curriculum_fuer_bezug(db: AsyncSession, curriculum_id: UUID, user) -> ContextNode:
    """Das Curriculum, wenn diese Person es als Bezug setzen darf (Schreibrecht wie im Editor).

    :raises HTTPException: 404 ohne Curriculum oder ohne Zugang.
    """
    cur = await zugang(db, user, curriculum_id, schreiben=False)
    if isinstance(cur, str):
        raise HTTPException(status_code=404, detail="Curriculum nicht gefunden")
    return cur


async def _lesbar(db: AsyncSession, curriculum_id: UUID | None, user) -> ContextNode | None:
    if curriculum_id is None:
        return None
    cur = await zugang(db, user, curriculum_id, schreiben=False)
    return None if isinstance(cur, str) else cur


async def bezug_fuer_anzeige(db: AsyncSession, curriculum_id: UUID | None, user) -> dict | None:
    """Was der Kopf des Chats zeigt und wohin er verlinkt; None ohne Bezug oder Zugang."""
    cur = await _lesbar(db, curriculum_id, user)
    if cur is None:
        return None
    return {"curriculum_id": str(cur.id), "titel": cur.title, "entwurf": cur.status == ENTWURF}


async def bezugszeile(db: AsyncSession, curriculum_id: UUID | None, user) -> str | None:
    """Systemzeile für den Assistenten — neu geprüft bei jedem Aufbau des Prompts."""
    cur = await _lesbar(db, curriculum_id, user)
    if cur is None:
        return None
    meta = cur.metadata_ or {}
    fach = meta.get("fach")
    if not fach and cur.subject_id:
        fach = await db.scalar(sa.select(Subject.name).where(Subject.id == cur.subject_id))
    teile = [t for t in (fach, f"Kl. {meta['jahrgangsstufe']}" if meta.get("jahrgangsstufe") else None,
                         f"BP {meta['bp_version']}" if meta.get("bp_version") else None) if t]
    stand = "Entwurf" if cur.status == ENTWURF else "veröffentlicht — nur lesen; zum Ändern „Als Entwurf kopieren“"
    return (f"Bezugscurriculum dieser Unterhaltung: „{cur.title}“ ({', '.join(teile)}; {stand}). "
            "Die Curriculum-Funktionen arbeiten ohne curriculum_id an diesem.")


async def bezug_setzen(db: AsyncSession, conversation_id: UUID | None, user, curriculum_id: UUID) -> None:
    """Setzt den Bezug an der eigenen Konversation (aus `waehle_curriculum`, `lege_curriculum_an`).

    Der Stundenbezug fällt dabei weg: Eine Unterhaltung arbeitet an einer Stunde oder an einem
    Curriculum, nicht an beidem.
    """
    if conversation_id is None:
        return
    await db.execute(sa.update(Conversation).where(
        Conversation.id == conversation_id, Conversation.pseudonym == user.sub,
    ).values(curriculum_node_id=curriculum_id, stunde_node_id=None))


# ── Einstieg aus der Assistentenliste (E18): finden, wählen, anlegen ─────────

_SCHULARTEN = {"GYM": "Gymnasium", "RS": "Realschule", "GMS": "Gemeinschaftsschule",
               "GS": "Grundschule", "BSO": "Berufsschule"}
TREFFER_MAX = 30


async def _faecher(db: AsyncSession, user, fach: str | None) -> list[Subject]:
    """Fächer, in denen die Person Curricula bearbeiten darf (Admin: alle), gefiltert nach `fach`
    (Name oder Kürzel, ein Teil genügt)."""
    from app.context.service import fachschafts_faecher

    q = sa.select(Subject).order_by(Subject.name)
    if "admin" not in (user.roles or ()):
        ids = await fachschafts_faecher(db, user.sub)
        if not ids:
            return []
        q = q.where(Subject.id.in_(ids))
    faecher = (await db.execute(q)).scalars().all()
    if fach and fach.strip():
        f = fach.strip().lower()
        faecher = [s for s in faecher if f in (s.name or "").lower() or f == (s.fach_code or "").lower()]
    return list(faecher)


def _band_passt(cur: ContextNode, jahrgangsstufe: str | None) -> bool:
    from app.context.grades import parse_grade_band

    lo, hi = parse_grade_band(jahrgangsstufe)
    if lo is None:
        return True
    if cur.min_grade is None or cur.max_grade is None:
        return True
    return cur.min_grade <= hi and cur.max_grade >= lo


async def _fassungen(db: AsyncSession, subject_id: int) -> list[dict]:
    from app.context.editions import BP_STATUS_CURRICULUM, KUENFTIG

    zeilen = (await db.execute(sa.select(ContextNode.bp_version, ContextNode.status).where(
        ContextNode.content_type == "fachplan", ContextNode.subject_id == subject_id,
        ContextNode.status.in_(BP_STATUS_CURRICULUM)).distinct())).all()
    aus: dict[str, dict] = {}
    for v, st in zeilen:
        if v and (v not in aus or st == "active"):
            aus[v] = {"bp_version": v, **({"kuenftig": True} if st == KUENFTIG else {})}
    return sorted(aus.values(), key=lambda x: x["bp_version"])


async def curricula_finden(db: AsyncSession, user, fach: str | None, jahrgangsstufe: str | None) -> dict:
    from app.context.curriculum_entwurf import LESBARE_STATUS

    faecher = await _faecher(db, user, fach)
    if not faecher:
        return {"curricula": [], "faecher": [],
                "hinweis": "Kein passendes Fach, in dem du Curricula bearbeiten darfst (Mitglied der Fachschaft)."}
    namen = {s.id: s.name for s in faecher}
    curricula = (await db.execute(sa.select(ContextNode).where(
        ContextNode.content_type == "curriculum", ContextNode.subject_id.in_(list(namen)),
        ContextNode.status.in_(LESBARE_STATUS)).order_by(ContextNode.subject_id, ContextNode.min_grade,
                                                         ContextNode.title))).scalars().all()
    curricula = [c for c in curricula if _band_passt(c, jahrgangsstufe)]
    entwuerfe = {(c.metadata_ or {}).get("kopie_von"): c.id for c in curricula
                 if c.status == ENTWURF and (c.metadata_ or {}).get("kopie_von")}
    liste = []
    for c in curricula[:TREFFER_MAX]:
        meta = c.metadata_ or {}
        eintrag = {"curriculum_id": str(c.id), "titel": c.title, "fach": namen.get(c.subject_id),
                   "jahrgangsstufe": meta.get("jahrgangsstufe"), "bp_version": meta.get("bp_version"),
                   "status": "Entwurf" if c.status == ENTWURF else "veröffentlicht"}
        if c.status != ENTWURF and (e := entwuerfe.get(str(c.id))):
            eintrag["offener_entwurf_id"] = str(e)
        liste.append(eintrag)
    return {
        "curricula": liste,
        **({"weitere": len(curricula) - TREFFER_MAX} if len(curricula) > TREFFER_MAX else {}),
        "faecher": [{"fach": s.name, "fassungen": await _fassungen(db, s.id)} for s in faecher[:10]],
    }


async def curriculum_waehlen(db: AsyncSession, user, curriculum_id: UUID, kopieren: bool) -> tuple[ContextNode | None, dict]:
    """(Curriculum für den Bezug, Antwort). Ein veröffentlichtes mit offenem Entwurf führt zum
    Entwurf; ohne Entwurf wird es Bezug zum Lesen, mit `kopieren` als Entwurf kopiert."""
    from app.context.curriculum_entwurf import darf_entwurf
    from app.context.relink import duplicate_curriculum
    from app.context.router import _offener_entwurf

    cur = await zugang(db, user, curriculum_id, schreiben=False)
    if isinstance(cur, str):
        return None, {"error": cur}
    if cur.status == ENTWURF:
        return cur, {}
    if (offen := await _offener_entwurf(db, cur.id)) is not None:
        return offen, {"hinweis": "Zu diesem Curriculum gibt es schon einen Entwurf — du arbeitest in ihm weiter."}
    if not kopieren:
        return cur, {"hinweis": "Veröffentlicht: nur lesen. Zum Ändern nach Zustimmung der Lehrkraft "
                                "waehle_curriculum mit als_entwurf_kopieren=true."}
    if not await darf_entwurf(db, cur.subject_id, user):
        return None, {"error": "Kopieren darf die Fachschaft des Fachs."}
    neu_id, _ = await duplicate_curriculum(db, cur.id, owner=user.sub, titel=cur.title)
    return await db.get(ContextNode, neu_id), {"hinweis": "Als Entwurf kopiert. Veröffentlicht wird er in der "
                                                          "Curriculum-Ansicht; dann ersetzt er das Original."}


async def curriculum_neu(db: AsyncSession, user, fach: str, jahrgangsstufe: str,
                         bp_version: str | None, band: str | None = None) -> tuple[ContextNode | None, dict]:
    """Legt einen leeren Entwurf an — nach Zustimmung. Kein zweites Curriculum für dasselbe Band
    und dieselbe Fassung: Dann nennt die Antwort das vorhandene.

    Parallele Bänder (Oberstufe, 0.46): Ohne `band` fragt die Antwort nach, welches."""
    import re

    from app.context.curriculum_entwurf import LESBARE_STATUS, curriculum_anlegen
    from app.context.editions import BP_STATUS_CURRICULUM
    from app.context.grades import parse_grade_band

    lo, hi = parse_grade_band(jahrgangsstufe)
    if lo is None:
        return None, {"error": f"„{jahrgangsstufe}“ ist keine Jahrgangsstufe (etwa „7“ oder „7/8“)."}
    faecher = await _faecher(db, user, fach)
    if len(faecher) != 1:
        return None, {"error": "Fach nicht eindeutig." if faecher else "Kein Fach, in dem du Curricula anlegen darfst.",
                      **({"faecher": [s.name for s in faecher]} if faecher else {})}
    subj = faecher[0]
    fassungen = await _fassungen(db, subj.id)
    if bp_version is None:
        if len(fassungen) == 1:
            bp_version = fassungen[0]["bp_version"]
        else:
            return None, {"error": "Welche Bildungsplan-Fassung? Frage die Lehrkraft.", "fassungen": fassungen}
    plan = (await db.execute(sa.select(ContextNode).where(
        ContextNode.content_type == "fachplan", ContextNode.subject_id == subj.id,
        ContextNode.bp_version == bp_version, ContextNode.status.in_(BP_STATUS_CURRICULUM),
    ).order_by(ContextNode.status != "active").limit(1))).scalar_one_or_none()
    if plan is None:
        return None, {"error": f"Für {subj.name} gibt es keinen Bildungsplan der Fassung {bp_version}. "
                               "Schreibe kein Curriculum.", "fassungen": fassungen}
    from app.context.curriculum_abdeckung import baender_fuer

    gefunden, kandidaten = await baender_fuer(db, subj.id, bp_version, lo, hi, band)
    if len(kandidaten) > 1 and gefunden is None:
        return None, {"error": "Zu diesen Stufen gibt es im Bildungsplan mehrere Bänder. Frage die "
                               "Lehrkraft, für welches das Curriculum gilt, und gib es als band an.",
                      "baender": [b.schluessel for b in kandidaten]}
    band = gefunden.schluessel if gefunden is not None and len(kandidaten) > 1 else None
    vorhanden = [c for c in (await db.execute(sa.select(ContextNode).where(
        ContextNode.content_type == "curriculum", ContextNode.subject_id == subj.id,
        ContextNode.status.in_(LESBARE_STATUS)))).scalars().all()
        if (c.metadata_ or {}).get("bp_version") == bp_version and (c.min_grade, c.max_grade) == (lo, hi)
        and (band is None or (c.metadata_ or {}).get("band") in (None, band))]
    if vorhanden:
        return None, {"error": "Für dieses Band und diese Fassung gibt es schon ein Curriculum — wähle es mit waehle_curriculum.",
                      "vorhanden": [{"curriculum_id": str(c.id), "titel": c.title,
                                     "status": "Entwurf" if c.status == ENTWURF else "veröffentlicht"} for c in vorhanden]}
    m = re.search(r"_(GYM|RS|GMS|GS|BSO)_", (plan.metadata_ or {}).get("bp_id") or "")
    cur = await curriculum_anlegen(
        db, plan, user, fach_code=subj.fach_code or "", schulart=_SCHULARTEN.get(m.group(1), m.group(1)) if m else "",
        jahrgangsstufe=jahrgangsstufe.strip(), bp_version=bp_version, titel=f"{subj.name} Kl. {jahrgangsstufe.strip()}")
    cur.metadata_ = {**(cur.metadata_ or {}), "fach": subj.name, **({"band": band} if band else {})}
    await db.flush()
    return cur, {"hinweis": "Leerer Entwurf angelegt."}
