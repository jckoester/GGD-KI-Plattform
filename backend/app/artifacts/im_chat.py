"""Produkte im Chat (0.41, Päckchen AN, Schritt 10; Plan F1 a, F2 a).

Ein Produkt aus der eigenen Werkstatt lässt sich per `@` (oder „Im Chat verwenden“ am Produkt)
an eine Konversation hängen. Der Chat legt dann bei jeder Frage seine **Quelle** bei — im
selben Abschnitt wie angeheftete Bausteine („Explizit hinzugefügter Kontext“).

- **Nur Arten mit lesbarer Quelle:** Dokument (Markdown) und Diagramme (Quelltext). Ein Bild
  trüge nur seinen Prompt bei, eine Datei gar nichts.
- **Nur Eigenes:** beim Anhängen geprüft und beim Laden noch einmal (`owner_pseudonym`), damit
  ein Produkt, das jemand anderem gehört, nie in einen Prompt gerät.
- **Längengrenze** je Produkt (`MAX_ZEICHEN`), mit einem Satz, dass gekürzt wurde. Ein langes
  Dokument soll die Frage nicht verdrängen.

Rollenoffen: Für Schüler:innen ist das seit Schritt 9 der Weg, eigene Arbeiten dem Assistenten
mitzugeben (das Anheften von Bausteinen bleibt Lehrkraft-Sache).
"""
from __future__ import annotations

from typing import Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Artifact, ChatArtifact

# Art → Name für das Modell und Zaun des Quelltexts (`None`: Markdown, ohne Zaun).
ANHAENGBAR: dict[str, tuple[str, str | None]] = {
    "document": ("Dokument", None),
    "mermaid": ("Diagramm (Mermaid)", "mermaid"),
    "circuit": ("Schaltplan (CircuiTikZ)", "circuitikz"),
    "plot": ("Funktionsgraph", "plot"),
    "smiles": ("Strukturformel (SMILES)", "smiles"),
}

MAX_ZEICHEN = 12_000
GEKUERZT = "[… gekürzt — der Rest dieses Produkts liegt nicht vor.]"


def ist_anhaengbar(artifact: Artifact) -> bool:
    return (
        artifact.kind in ANHAENGBAR
        and artifact.derived_from is None
        and bool((artifact.source or "").strip())
    )


def abschnitt(artifact: Artifact) -> str:
    """Ein Produkt als Abschnitt für den Prompt — Überschrift, Art, Quelle (gekürzt)."""
    art, zaun = ANHAENGBAR[artifact.kind]
    quelle = (artifact.source or "").strip()
    gekuerzt = len(quelle) > MAX_ZEICHEN
    if gekuerzt:
        quelle = quelle[:MAX_ZEICHEN].rstrip()
    if zaun:
        quelle = f"```{zaun}\n{quelle}\n```"
    zeilen = [f"### {artifact.title} — {art} aus der eigenen Werkstatt", quelle]
    if gekuerzt:
        zeilen.append(GEKUERZT)
    return "\n".join(zeilen) + "\n"


async def angehaengte(db: AsyncSession, chat_id: UUID | None, pseudonym: str) -> list[Artifact]:
    """Die Produkte dieser Konversation, in der Reihenfolge des Anhängens — nur eigene."""
    if chat_id is None:
        return []
    treffer = await db.execute(
        sa.select(Artifact)
        .join(ChatArtifact, ChatArtifact.artifact_id == Artifact.id)
        .where(
            ChatArtifact.chat_id == chat_id,
            Artifact.owner_pseudonym == pseudonym,
            Artifact.kind.in_(list(ANHAENGBAR)),
        )
        .order_by(ChatArtifact.added_at, Artifact.id)
    )
    return list(treffer.scalars())


async def anhaengbare(
    db: AsyncSession, pseudonym: str, q: str = "", *, limit: int = 8
) -> Sequence[Artifact]:
    """Für das `@`-Dropdown: eigene Produkte mit Quelle, Titel passt zu ``q``."""
    abfrage = (
        sa.select(Artifact)
        .where(
            Artifact.owner_pseudonym == pseudonym,
            Artifact.kind.in_(list(ANHAENGBAR)),
            Artifact.derived_from.is_(None),
            sa.func.length(sa.func.trim(sa.func.coalesce(Artifact.source, ""))) > 0,
        )
        .order_by(sa.func.coalesce(Artifact.updated_at, Artifact.created_at).desc(), Artifact.id)
        .limit(limit)
    )
    suche = (q or "").strip()
    if suche:
        muster = "%" + suche.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        abfrage = abfrage.where(Artifact.title.ilike(muster, escape="\\"))
    return list((await db.execute(abfrage)).scalars())


async def beim_anlegen_anhaengen(
    db: AsyncSession, chat_id: UUID, pseudonym: str, ids: Sequence[UUID]
) -> int:
    """Produkte an eine eben angelegte Konversation hängen — vor dem Kontextaufbau.

    Fremdes und nicht Anhängbares fällt still heraus (die Oberfläche bietet es nicht an).
    Committet nicht; das tut der Chat mit der Konversation. Gibt die Zahl der Anhänge zurück.
    """
    zahl = 0
    for artifact_id in dict.fromkeys(ids):
        r = await db.get(Artifact, artifact_id)
        if r is None or r.owner_pseudonym != pseudonym or not ist_anhaengbar(r):
            continue
        db.add(ChatArtifact(chat_id=chat_id, artifact_id=r.id))
        zahl += 1
    if zahl:
        await db.flush()
    return zahl
