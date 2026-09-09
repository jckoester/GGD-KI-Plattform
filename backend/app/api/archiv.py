"""Frühere Unterrichtsgruppen — das Archiv der Gruppenübersicht (AP6).

**Das Problem, das es löst.** `sync_groups` arbeitet als *Immediate Mirror*: Beim
Login fallen alle Mitgliedschaften, die nicht mehr im Token stehen. Mit dem neuen
Schuljahr verschwinden die Gruppen des alten damit von selbst aus der Oberfläche —
und mit ihnen Jahrespläne, Stundenentwürfe und Chats, die weiter in der Datenbank
liegen. Sie sind nicht gelöscht, sie sind unerreichbar.

**Warum der Anker der eigene Inhalt ist und nicht die Mitgliedschaft.** Die
Mitgliedschaft ist weg; sie taugt nicht mehr als Nachweis. Sie wiederzubeleben wäre
zudem die unsichere Variante: Mitgliedschaft öffnet auch *fremdes*
gruppen-freigegebenes Material. Der inhaltsbasierte Weg zeigt nur, was der Person
selbst gehört — eigene Knoten (`owner_pseudonym`) und eigene Konversationen
(`pseudonym`). Damit braucht das Archiv **keine** Migration und kein
Schuljahr-Kennzeichen an `groups`.
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.models import ContextNode, Conversation, Group, GroupMembership
from app.db.session import get_db

router = APIRouter(prefix="/archive", tags=["archive"])

# Was im Archiv gezählt wird. Andere Knotentypen der Gruppe (Arbeitsblätter,
# Aufgaben …) erscheinen über „Meine Bausteine", das kennt keine Schuljahresgrenze.
GEZAEHLTE_TYPEN = ("jahresplan", "unterrichtseinheit", "unterrichtsstunde")


class FruehereGruppe(BaseModel):
    group_id: int
    name: str
    subject_id: Optional[int] = None
    schuljahr: Optional[str] = None
    bausteine: int
    chats: int


class ArchivAntwort(BaseModel):
    items: list[FruehereGruppe]


def _eigene_gruppen_unterabfrage(pseudonym: str):
    return (
        sa.select(GroupMembership.group_id)
        .where(GroupMembership.pseudonym == pseudonym)
        .scalar_subquery()
    )


@router.get("/groups", response_model=ArchivAntwort)
async def list_former_groups(
    subject_id: Optional[int] = None,
    current_user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ArchivAntwort:
    """Gruppen, in denen ich Eigenes habe, ohne noch Mitglied zu sein.

    `subject_id` verengt auf ein Fach — für den Hinweis auf der Fachseite.

    Das Schuljahr kommt aus dem Inhalt (`context_nodes.schuljahr`), nicht aus einer
    Spalte an `groups`: Die Gruppe selbst weiß nicht, wann sie gelebt hat, ihre
    Jahrespläne schon. Fehlt die Angabe, bleibt das Feld leer — eine geratene
    Jahreszahl wäre schlechter als keine.
    """
    eigene = _eigene_gruppen_unterabfrage(current_user.sub)

    # Eigene Planungsknoten je Gruppe. `write_scope_group_id` ist der Träger — dort
    # hängen Jahresplan, Einheit und Stunde (siehe `app/planning/router.py`).
    knoten = (
        sa.select(
            ContextNode.write_scope_group_id.label("group_id"),
            sa.func.count().label("anzahl"),
            sa.func.max(ContextNode.schuljahr).label("schuljahr"),
        )
        .where(
            ContextNode.owner_pseudonym == current_user.sub,
            ContextNode.status == "active",
            ContextNode.content_type.in_(GEZAEHLTE_TYPEN),
            ContextNode.write_scope_group_id.is_not(None),
            ContextNode.write_scope_group_id.not_in(eigene),
        )
        .group_by(ContextNode.write_scope_group_id)
        .subquery()
    )

    chats = (
        sa.select(
            Conversation.group_id.label("group_id"),
            sa.func.count().label("anzahl"),
        )
        .where(
            Conversation.pseudonym == current_user.sub,
            Conversation.group_id.is_not(None),
            Conversation.hidden_by_user.is_(False),
            Conversation.group_id.not_in(eigene),
        )
        .group_by(Conversation.group_id)
        .subquery()
    )

    # Beide Quellen zusammenführen: Eine Gruppe kann nur Chats haben oder nur
    # Bausteine. Ein Join über eine von beiden verlöre die jeweils andere Hälfte.
    ids = sa.union(
        sa.select(knoten.c.group_id), sa.select(chats.c.group_id)
    ).subquery()

    stmt = (
        sa.select(
            Group.id,
            Group.name,
            Group.subject_id,
            sa.func.coalesce(knoten.c.anzahl, 0),
            sa.func.coalesce(chats.c.anzahl, 0),
            knoten.c.schuljahr,
        )
        .select_from(ids)
        .join(Group, Group.id == ids.c.group_id)
        .outerjoin(knoten, knoten.c.group_id == Group.id)
        .outerjoin(chats, chats.c.group_id == Group.id)
        .where(Group.type == "teaching_group")
        .order_by(knoten.c.schuljahr.desc().nulls_last(), Group.name)
    )
    if subject_id is not None:
        stmt = stmt.where(Group.subject_id == subject_id)

    rows = (await db.execute(stmt)).all()
    return ArchivAntwort(
        items=[
            FruehereGruppe(
                group_id=r[0], name=r[1], subject_id=r[2],
                bausteine=r[3], chats=r[4], schuljahr=r[5],
            )
            for r in rows
        ]
    )
