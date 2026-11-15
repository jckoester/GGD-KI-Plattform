"""Entwürfe von Curricula (0.45, Päckchen AP Teil A, E7, E8, E11).

Ein Entwurf ist ein Curriculum-Baum (`curriculum`, `kapitel`, `lernsequenz`) mit
`status = 'draft'`. Ihn sehen und bearbeiten nur die Mitglieder der Fachschaft des Fachs und
Admins — mit der echten Rolle, nie in der Vorschau.

**Wo die Regel greift.** Die Listen- und Suchwege filtern auf `active` und schließen Entwürfe
damit ohnehin aus (Suche, Retrieval, Embeddings, Jahresplanung, „Meine Bausteine“). Diese
Datei ist für die Wege, die einen Knoten **direkt** holen: `_check_read_permission` und
`_check_write_permission` im Router (direkte Adresse, Umgebung, Kanten, allgemeines PATCH)
und die Curriculum-Endpunkte. Eine Regel, keine Kopien — wer eine neue Stelle braucht, ruft
:func:`pruefe_entwurf`.

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
# Ein Curriculum, das jemand lesen darf, ist `active` oder — für die Fachschaft — ein Entwurf.
LESBARE_STATUS = ("active", ENTWURF)


async def darf_entwurf(db: AsyncSession, subject_id: int | None, user) -> bool:
    """Ob die Person Entwürfe dieses Fachs sehen und bearbeiten darf (E7, E8).

    Admin, oder Lehrkraft in einer Fachschaft des Fachs (`fachschafts_faecher`, dieselbe Regel
    wie das Schreibrecht bei `write_scope = subject`). In der Vorschau sind die Rollen
    simuliert und die Mitgliedschaften auf die gewählte Gruppe beschränkt — beides fällt durch.
    """
    roles = getattr(user, "roles", None) or ()
    if "admin" in roles:
        return True
    if "teacher" not in roles or subject_id is None:
        return False
    from app.context.service import fachschafts_faecher

    return subject_id in await fachschafts_faecher(db, user.sub)


async def pruefe_entwurf(db: AsyncSession, subject_id: int | None, user) -> None:
    """404, wenn die Person den Entwurf nicht sehen darf.

    404 statt 403: Wer den Entwurf nicht sehen darf, erfährt auch nicht, dass es ihn gibt.
    """
    if not await darf_entwurf(db, subject_id, user):
        raise HTTPException(status_code=404, detail="Baustein nicht gefunden")


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
