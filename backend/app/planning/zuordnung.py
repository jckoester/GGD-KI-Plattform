"""Welche Stunde oder Unterrichtseinheit in einen Slot darf (Patch 0.12.x).

Ein Slot verweist über `ue_node_id` und `stunde_node_id` auf Knoten. Stammt ein solcher
Knoten aus einer anderen Gruppe, steht deren Planung im fremden Jahresplan — und eine
Bearbeitung in der einen Gruppe ändert still den Plan der anderen. Erlaubt ist deshalb
nur, was der Planer selbst anlegt: passender Typ, aktiv, Schreibrecht bei **dieser**
Gruppe. Dieselbe Definition wie `_load_units` (`router.py`) und `_load_ue_map`
(`assistant_tools.py`) — ⚠️ ändert sich dort etwas, gehört es hierher mit.

Entscheidung Jan, 03.10.2026: nur aus derselben Gruppe. Dieselbe Stunde in einer
Parallelklasse heißt kopieren, nicht verlinken.

Bis 0.12.0 prüften vier Wege das nicht: `PATCH /planning/slots/{id}` (beide Felder), die
Planungs-Operation `SetUnit` und das Werkzeug `assign_slots_to_unit` — die letzten beiden
mit IDs, die das Modell liefert.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContextNode

#: Feld am Slot → (content_type, Bezeichnung für die Meldung)
ARTEN = {
    "ue_node_id": ("unterrichtseinheit", "Unterrichtseinheit"),
    "stunde_node_id": ("unterrichtsstunde", "Unterrichtsstunde"),
}

_GRUPPEN_SCOPES = ("group", "group_teachers")


def gehoert_zur_gruppe(node: ContextNode, group_id: int) -> bool:
    return (
        node.write_scope in _GRUPPEN_SCOPES
        and node.write_scope_group_id == group_id
        and node.status == "active"
    )


async def fehler_fuer(
    db: AsyncSession, group_id: int, feld: str, node_id: Optional[UUID]
) -> Optional[str]:
    """Meldung, wenn `node_id` nicht in das Feld `feld` eines Slots dieser Gruppe darf.

    ``None`` heißt erlaubt — auch für ``node_id=None``: Lösen geht immer.

    Eine Meldung für alle drei Gründe (fehlt, falscher Typ, andere Gruppe): Wer eine ID
    einer fremden Gruppe schickt, soll nicht erfahren, ob es sie gibt.
    """
    if node_id is None:
        return None
    typ, bezeichnung = ARTEN[feld]
    node = await db.get(ContextNode, node_id)
    if node is None or node.content_type != typ or not gehoert_zur_gruppe(node, group_id):
        return f"{node_id} ist keine {bezeichnung} dieser Gruppe."
    return None
