"""Entwürfe von Curricula (0.45, Päckchen AP Teil A, E7, E8, E11; Lesen seit 0.52, AZ).

Ein Entwurf ist ein Curriculum-Baum (`curriculum`, `kapitel`, `lernsequenz`) mit
`status = 'draft'`. **Lesen** dürfen ihn alle Lehrkräfte und Admins (seit 0.52, hebt E7 auf),
**bearbeiten** nur die Mitglieder der Fachschaft des Fachs und Admins (E8) — beides mit der
echten Rolle, nie in der Vorschau. Zwei Regeln, :func:`darf_entwurf_lesen` und
:func:`darf_entwurf_bearbeiten`; ein Wächtertest hält die Leseregel aus schreibenden Wegen.

**Wo die Regel greift.** Die Listen- und Suchwege filtern auf `active` und schließen Entwürfe
damit ohnehin aus (Suche, Retrieval, Embeddings, Jahresplanung, „Meine Bausteine“). Diese
Datei ist für die Wege, die einen Knoten **direkt** holen: `_check_read_permission` und
`_check_write_permission` im Router (direkte Adresse, Umgebung, Kanten, allgemeines PATCH)
und die Curriculum-Endpunkte. Eine Regel, keine Kopien — wer eine neue Stelle braucht, ruft
:func:`pruefe_entwurf_lesen` oder :func:`pruefe_entwurf_bearbeiten`.

⚠️ Den Status eines Entwurfs ändert nur „Veröffentlichen“ (Schritt 4). Beide PATCH-Wege
weisen jeden Übergang von und nach `draft` ab (:func:`pruefe_statuswechsel`) — sonst
veröffentlichte, wer schreiben darf, ohne das Recht dazu.
"""
from __future__ import annotations

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

ENTWURF = "draft"
CURRICULUM_TYPEN = frozenset({"curriculum", "kapitel", "lernsequenz"})
# Ein Curriculum, das jemand lesen darf, ist `active` oder — für Lehrkräfte — ein Entwurf.
LESBARE_STATUS = ("active", ENTWURF)
NUR_FACHSCHAFT = "Entwürfe bearbeitet die Fachschaft des Fachs."


def darf_entwurf_lesen(user) -> bool:
    """Ob die Person Curriculum-Entwürfe lesen darf — alle Fächer (0.52, AZ; hebt E7 auf).

    Lehrkraft oder Admin. In der Vorschau trägt der Token `["student"]` und fällt durch.
    Entwürfe bleiben trotzdem aus Suche, Retrieval und Planung: Diese Wege filtern auf
    `active`, unabhängig vom Leserecht.
    """
    roles = getattr(user, "roles", None) or ()
    return "admin" in roles or "teacher" in roles


async def darf_entwurf_bearbeiten(db: AsyncSession, subject_id: int | None, user) -> bool:
    """Ob die Person Entwürfe dieses Fachs bearbeiten, anlegen und kopieren darf (E8).

    Admin, oder Lehrkraft in einer Fachschaft des Fachs (`fachschafts_faecher`, dieselbe Regel
    wie das Schreibrecht bei `write_scope = subject`). In der Vorschau sind die Rollen
    simuliert und die Mitgliedschaften auf die gewählte Gruppe beschränkt — beides fällt durch.
    Bis 0.52 hieß sie `darf_entwurf` und regelte auch das Lesen.
    """
    roles = getattr(user, "roles", None) or ()
    if "admin" in roles:
        return True
    if "teacher" not in roles or subject_id is None:
        return False
    from app.context.service import fachschafts_faecher

    return subject_id in await fachschafts_faecher(db, user.sub)


# ── Schreiben und Veröffentlichen (Schritt 4, E9, E10, E13, E16) ──────────────


def fachvorsitz_zugeordnet() -> bool:
    """Ob der Rolle `fachvorsitz` eine SSO-Gruppe zugeordnet ist (E9).

    Die Zuordnung schaltet die Freigabe ein: Mit ihr veröffentlichen und ändern veröffentlichte
    Curricula nur Fachvorsitzende und Admins, ohne sie alle Mitglieder der Fachschaft. Gelesen
    wird `auth.yaml` wie beim Login — bei jeder Prüfung frisch (wenige Zeilen YAML), damit
    eine geänderte Zuordnung ohne Neustart greift und Tests sie umstellen können.
    """
    from app.auth.config import load_auth_config
    from app.config import settings

    try:
        return "fachvorsitz" in load_auth_config(settings.auth_config_path).group_role_map_dict.values()
    except Exception:  # keine oder kaputte auth.yaml: die offene Regel, wie vor 0.45
        return False


def schreibrecht(status: str, subject_id: int | None, roles, fachschaften: set[int],
                 zugeordnet: bool) -> bool:
    """**Die** Regel für Curriculum, Kapitel und Lernsequenz — ohne Datenbank.

    - Admin: immer.
    - Sonst nur Lehrkräfte in einer Fachschaft des Fachs (E8; `fachschafts_faecher`, jede
      Fachschaftsgruppe des Fachs — bis 0.45 prüfte `_require_curriculum_write` nur **die**
      Gruppe am Knoten und wich damit vom allgemeinen Schreibrecht ab).
    - Entwurf: diese Lehrkräfte (E7, E8).
    - Veröffentlicht oder archiviert (ändern, archivieren, reaktivieren, veröffentlichen):
      mit zugeordneter Fachvorsitz-Gruppe nur, wer die Rolle hat (E13, E16), sonst alle.
    """
    roles = roles or ()
    if "admin" in roles:
        return True
    if "teacher" not in roles or subject_id is None or subject_id not in fachschaften:
        return False
    if status == ENTWURF:
        return True
    return not zugeordnet or "fachvorsitz" in roles


async def _fachschaften(db: AsyncSession, user) -> set[int]:
    from app.context.service import fachschafts_faecher

    return await fachschafts_faecher(db, user.sub)


async def darf_schreiben(db: AsyncSession, status: str, subject_id: int | None, user) -> bool:
    roles = getattr(user, "roles", None) or ()
    if "admin" in roles:
        return True
    return schreibrecht(status, subject_id, roles, await _fachschaften(db, user), fachvorsitz_zugeordnet())


async def darf_veroeffentlichen(db: AsyncSession, subject_id: int | None, user) -> bool:
    """Veröffentlichen ist das Recht am veröffentlichten Curriculum (E9)."""
    return await darf_schreiben(db, "active", subject_id, user)


async def darf_loeschen(db: AsyncSession, node, user) -> bool:
    """Ein Curriculum als Ganzes löschen (E12).

    Entwurf: wer ihn angelegt hat (solange sie ihn noch bearbeiten darf, also in der Fachschaft
    ist), Fachvorsitzende und Admins — nicht jedes Mitglied der Fachschaft. „Fachvorsitzende“
    heißt wie beim Veröffentlichen: ohne zugeordnete Gruppe die Fachschaft (E9).
    Veröffentlicht: wer es ändern darf (E13). Teile eines Entwurfs (Kapitel, Lernsequenzen)
    löscht der Editor — dafür gilt das Bearbeitungsrecht, nicht diese Regel.
    """
    from app.auth.vorschau import eigenes_zaehlt

    if node.status != ENTWURF:
        return await darf_schreiben(db, node.status, node.subject_id, user)
    if not await darf_entwurf_bearbeiten(db, node.subject_id, user):
        return False
    if node.owner_pseudonym == user.sub and eigenes_zaehlt(user.sub):
        return True
    return await darf_veroeffentlichen(db, node.subject_id, user)


def wer_veroeffentlicht() -> str:
    """Für die Oberfläche, statt des Knopfs (Punkt 7)."""
    if fachvorsitz_zugeordnet():
        return "Fachvorsitzende dieser Fachschaft und Admins"
    return "Mitglieder der Fachschaft und Admins"


def pruefe_entwurf_lesen(user) -> None:
    """404, wenn die Person den Entwurf nicht lesen darf.

    404 statt 403: Wer den Entwurf nicht sehen darf, erfährt auch nicht, dass es ihn gibt.
    """
    if not darf_entwurf_lesen(user):
        raise HTTPException(status_code=404, detail="Baustein nicht gefunden")


async def pruefe_entwurf_bearbeiten(db: AsyncSession, subject_id: int | None, user) -> None:
    """404, wenn die Person den Entwurf nicht einmal lesen darf; 403, wenn sie ihn liest, aber
    nicht bearbeiten darf (seit 0.52 — vorher gab es nur 404)."""
    pruefe_entwurf_lesen(user)
    if not await darf_entwurf_bearbeiten(db, subject_id, user):
        raise HTTPException(status_code=403, detail=NUR_FACHSCHAFT)


def pruefe_statuswechsel(alt: str, neu: str | None) -> None:
    """422 für jeden Wechsel von oder nach `draft` über die allgemeinen Wege."""
    if neu is None or neu == alt:
        return
    if ENTWURF in (alt, neu):
        raise HTTPException(
            status_code=422,
            detail="Einen Entwurf veröffentlicht nur „Veröffentlichen“ im Curriculum-Editor.",
        )


def pruefe_kante(von_status: str, zu_status: str) -> None:
    """Auf einen Entwurf zeigen nur Teile eines Entwurfs.

    Sonst hinge etwa eine Unterrichtseinheit an einem Kapitel, das es für alle anderen noch
    nicht gibt — und die Planung liest Kapitel ohne Statusprüfung.
    """
    if zu_status == ENTWURF and von_status != ENTWURF:
        raise HTTPException(
            status_code=422,
            detail="Auf einen Entwurf verweisen nur Teile desselben Entwurfs.",
        )


TEILE = frozenset({"kapitel", "lernsequenz"})


def pruefe_anlegen(content_type: str | None, status: str) -> None:
    """Als Entwurf neu anlegen lassen sich nur Teile — ein Curriculum entsteht über
    `POST /context/curricula/new` (immer als Entwurf) oder als Kopie."""
    if status == ENTWURF and content_type not in TEILE:
        raise HTTPException(
            status_code=422, detail="Als Entwurf lassen sich nur Kapitel und Lernsequenzen anlegen.")


async def erbe_entwurf(db: AsyncSession, kind, eltern, relation: str) -> None:
    """Ein frisch angelegter Teil, der in einen Entwurf gehängt wird, wird selbst Entwurf.

    Frisch heißt: noch ohne jede Kante. Ein Kapitel, das schon irgendwo hängt — in einem
    veröffentlichten Curriculum, an einer Einheit —, verschwände sonst für alle anderen; diese
    Kante weist :func:`pruefe_kante` danach ab.
    """
    if (relation != "part_of" or eltern.status != ENTWURF or kind.status != "active"
            or kind.content_type not in TEILE):
        return
    from app.db.models import ContextEdge

    hat_kanten = (await db.execute(sa.select(sa.exists().where(sa.or_(
        ContextEdge.from_node_id == kind.id, ContextEdge.to_node_id == kind.id))))).scalar()
    if not hat_kanten:
        kind.status = ENTWURF


async def letzte_aenderung(db: AsyncSession, curriculum_ids) -> dict:
    """Je Curriculum die jüngste Änderung an ihm, seinen Kapiteln und Lernsequenzen."""
    from sqlalchemy.orm import aliased

    from app.db.models import ContextEdge, ContextNode

    kap, ls = aliased(ContextNode), aliased(ContextNode)
    e1, e2 = aliased(ContextEdge), aliased(ContextEdge)
    cur = aliased(ContextNode)
    zeilen = (await db.execute(
        sa.select(cur.id, sa.func.greatest(
            sa.func.max(cur.updated_at), sa.func.max(kap.updated_at), sa.func.max(ls.updated_at)))
        .select_from(cur)
        .outerjoin(e1, sa.and_(e1.to_node_id == cur.id, e1.relation == "part_of"))
        .outerjoin(kap, sa.and_(kap.id == e1.from_node_id, kap.content_type == "kapitel"))
        .outerjoin(e2, sa.and_(e2.to_node_id == kap.id, e2.relation == "part_of"))
        .outerjoin(ls, sa.and_(ls.id == e2.from_node_id, ls.content_type == "lernsequenz"))
        .where(cur.id.in_(list(curriculum_ids)))
        .group_by(cur.id)
    )).all()
    return {cid: zeit for cid, zeit in zeilen}


async def curriculum_anlegen(db: AsyncSession, fachplan_node, user, *, fach_code: str, schulart: str,
                             jahrgangsstufe: str, bp_version: str, schule: str = "",
                             titel: str | None = None, band: str | None = None):
    """Ein neues, leeres Curriculum als Entwurf am Fachplan — für `POST /curricula/new` und den
    Assistenten (`lege_curriculum_an`, 0.46). Kein Commit.

    Recht: Mitglied der Fachschaft des Fachs. **Admins sind ausgenommen — bewusst**
    (Entscheidung Jan, 05.11.2026, 0.34): eine Verwaltungsbefugnis, keine Abweichung von der
    Rollenregel „Admin verhält sich wie eine Lehrkraft“. Existiert für das Fach gar keine
    Fachschaft, wird nicht geprüft.

    Idempotent je Person, Fach, Jahrgangsstufe, Fassung und Band des Bildungsplans: Ein zweiter
    Aufruf liefert das vorhandene Curriculum mit demselben Schlüssel — Entwurf oder
    veröffentlicht. Bis 0.46 suchte die Prüfung nur veröffentlichte; weil neue Curricula seit
    0.45 Entwürfe sind, griff sie nie, und ein zweiter Aufruf legte ein Doppel an.
    `band` (parallele Bänder der Oberstufe) steht nicht im Schlüssel — der wird beim Ändern der
    Jahrgangsstufe segmentweise umgeschrieben —, sondern wird beim Vergleich mitgeprüft.
    """
    from fastapi import HTTPException

    from app.context.grades import parse_grade_band
    from app.context.service import get_subject_department_group_id, is_subject_department_member
    from app.db.models import ContextEdge, ContextNode

    subject_id = fachplan_node.subject_id
    if not subject_id:
        raise HTTPException(status_code=422,
                            detail="Fachplan nicht mit einem Fach verknüpft — bitte Bildungsplan neu importieren")
    department_group_id = await get_subject_department_group_id(db, subject_id)
    if department_group_id is not None and "admin" not in user.roles:
        if not await is_subject_department_member(db, subject_id, user.sub):
            raise HTTPException(status_code=403, detail="Keine Berechtigung - du musst Mitglied der Fachschaft sein")

    import_key = f"new_{user.sub}_{fach_code}_{jahrgangsstufe}_{bp_version}"
    for vorhanden in (await db.execute(sa.select(ContextNode).where(
            ContextNode.content_type == "curriculum",
            ContextNode.metadata_["import_key"].astext == import_key,
            ContextNode.status.in_(LESBARE_STATUS)).order_by(ContextNode.created_at))).scalars():
        if (vorhanden.metadata_ or {}).get("band") == band:
            return vorhanden

    lo, hi = parse_grade_band(jahrgangsstufe)
    curriculum = ContextNode(
        category="knowledge", content_type="curriculum",
        title=titel or f"{fach_code} Kl. {jahrgangsstufe}", content=None,
        read_scope="school", write_scope="subject", write_scope_group_id=department_group_id,
        subject_id=subject_id, min_grade=lo, max_grade=hi, owner_pseudonym=user.sub,
        metadata_={
            # Geschäftsschlüssel des Bildungsplans — konsistent mit dem Import-Pfad. Kann fehlen,
            # wenn der Fachplan-Knoten keinen trägt.
            "fachplan_id": (fachplan_node.metadata_ or {}).get("fachplan_id"),
            # Node-UUID des Fachplans — redundant zur part_of-Kante, praktisch für Lookups.
            "fachplan_node_id": str(fachplan_node.id),
            "bp_version": bp_version, "schule": schule, "fach_code": fach_code,
            "schulart": schulart, "jahrgangsstufe": jahrgangsstufe, "import_key": import_key,
            **({"band": band} if band else {}),
        },
        # Jedes neue Curriculum ist ein Entwurf (0.45, F2/E11): Ein leeres Curriculum ist nie
        # fertig. Sichtbar für alle wird es erst über „Veröffentlichen“.
        status=ENTWURF,
    )
    db.add(curriculum)
    await db.flush()
    db.add(ContextEdge(from_node_id=curriculum.id, to_node_id=fachplan_node.id, relation="part_of", metadata_={}))
    await db.flush()
    return curriculum
