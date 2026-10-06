"""Die Bausteine einer Antwort — was beim Antworten vorlag (0.14, Schritt 2).

**Gefunden, nicht verwendet.** Welche Bausteine das Modell tatsächlich benutzt hat, weiß
nur das Modell; danach zu fragen kostete einen zweiten Aufruf und lieferte wieder nur eine
Wahrscheinlichkeit. Festgehalten wird, was vorlag — deshalb heißt die Zeile unter der
Antwort „Kontext", nicht „Quellen" (Entscheidung Jan, 27.09.2026).

Zwei Herkünfte, in dieser Reihenfolge:

- ``vorab`` — die Grundschicht zur Frage (höchstens fünf, :func:`app.context.search.vorab`),
- ``werkzeug`` — was das Modell in einer Suchrunde zusätzlich bekam (``search_context_nodes``,
  ``list_context_nodes``).

⚠️ **Nicht dabei:** der Ankerkontext eines Assistenten (sein Gegenstand, nicht die Antwort
auf diese Frage, und er wechselt nicht von Nachricht zu Nachricht), angeheftete Knoten (die
hat die Person selbst gewählt) und der Lernstand.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContextNode, MessageContextNode

VORAB = "vorab"
WERKZEUG = "werkzeug"


@dataclass(frozen=True)
class Baustein:
    node_id: str
    titel: str
    content_type: str | None
    fach: str | None
    herkunft: str
    #: 1 − Kosinusdistanz, nur bei thematischen Vorab-Treffern. Ein Treffer über den Namen
    #: hat keine — er ist nicht ähnlich, er heißt so.
    aehnlichkeit: float | None = None


@dataclass
class Kontext:
    """Was :func:`app.context.service.kontext_fuer_frage` liefert: Prompt-Text und Bausteine."""

    text: str
    bausteine: list[Baustein] = field(default_factory=list)


def aus_treffern(treffer: Iterable, herkunft: str) -> list[Baustein]:
    """Suchtreffer (Dicts der Suchschicht) → Bausteine. Fremde Formen fallen heraus."""
    bausteine = []
    for t in treffer:
        if not isinstance(t, dict) or not t.get("node_id"):
            continue
        distanz = t.get("distanz")
        bausteine.append(Baustein(
            node_id=str(t["node_id"]),
            titel=t.get("title") or "",
            content_type=t.get("content_type"),
            fach=t.get("fach"),
            herkunft=herkunft,
            aehnlichkeit=None if distanz is None else round(1.0 - float(distanz), 3),
        ))
    return bausteine


def vereinige(*listen: Iterable[Baustein]) -> list[Baustein]:
    """Alle Listen hintereinander, jeder Baustein einmal — in der Reihenfolge des ersten
    Auftretens. Ein Baustein, der vorab da war und im Werkzeug wieder auftaucht, bleibt
    `vorab`: Er lag schon vor, bevor das Modell suchte."""
    gesehen: set[str] = set()
    ergebnis: list[Baustein] = []
    for liste in listen:
        for b in liste:
            if b.node_id in gesehen:
                continue
            gesehen.add(b.node_id)
            ergebnis.append(b)
    return ergebnis


async def speichere(db: AsyncSession, message_id: UUID, bausteine: list[Baustein]) -> None:
    """Die Bausteine an die Nachricht hängen. Committet nicht — der Aufrufer schreibt sie im
    selben Commit wie die Nachricht, sonst gäbe es Antworten ohne Bausteine und umgekehrt.

    ⚠️ **Nur Knoten, die es noch gibt.** Zwischen Suche und Speichern vergehen Sekunden; wird
    ein Baustein in der Zeit gelöscht, schlüge der Fremdschlüssel an — und mit ihm der
    ganze Commit, also auch die Antwort selbst. Ein fehlender Verweis ist das kleinere Übel.
    """
    if not bausteine:
        return
    ids = [UUID(b.node_id) for b in bausteine]
    vorhanden = set((await db.execute(
        sa.select(ContextNode.id).where(ContextNode.id.in_(ids))
    )).scalars().all())
    for position, b in enumerate(b for b in bausteine if UUID(b.node_id) in vorhanden):
        db.add(MessageContextNode(
            message_id=message_id,
            node_id=UUID(b.node_id),
            position=position,
            herkunft=b.herkunft,
            aehnlichkeit=b.aehnlichkeit,
        ))
