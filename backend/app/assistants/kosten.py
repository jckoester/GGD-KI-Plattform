"""Was eine Nachricht an einen Assistenten etwa kostet (0.27, Plan Schritt 10, F7′).

Der Modellwähler schätzt an einer **mittleren** Nachricht (`REFERENZ_NACHRICHT`, gemessen über
alle Chats). Ein Assistent schickt aber bei jeder Nachricht dazu seinen Prompt, die Bausteine
und die Kontext-Dokumente mit — im Extremfall 15 000 Token mehr. Die Marke des Modells allein
läge gerade bei Assistenten mit Dokumenten deutlich zu niedrig.

Deshalb: Referenznachricht **plus** feste Token des Assistenten, mal Eingabepreis des Modells.
Token werden wie beim Upload geschätzt (`len // 4`). Das bleibt eine Schätzung; abgerechnet
wird nach Verbrauch. Ohne bekannten Preis gibt es keine Zahl (`None`) — eine Null hieße
„kostenlos".

Später, wenn genug Gespräche da sind, könnte hier der Median der echten Kosten je Assistent
stehen (Plan F7′).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistants import bausteine as bausteine_modul
from app.assistants.sichtbarkeit import modell_des_assistenten
from app.db.models import Assistant, AssistantDocument
from app.litellm.modell_eigenschaften import REFERENZ_NACHRICHT, alle_eigenschaften


def _token(zeichen: int) -> int:
    return zeichen // 4


@dataclass
class Dokument:
    name: str
    groesse_bytes: int
    token: int


@dataclass
class Kosten:
    usd_je_nachricht: float | None = None
    usd_dokumente: float | None = None
    dokumente: list[Dokument] = field(default_factory=list)


async def kosten_je_assistent(db: AsyncSession, assistenten: list[Assistant]) -> dict[int, Kosten]:
    """Kostenschätzung und Dokumentliste je Assistent — zwei Abfragen für die ganze Liste."""
    if not assistenten:
        return {}
    eigenschaften = await alle_eigenschaften()
    zeilen = (await db.execute(
        sa.select(AssistantDocument.assistant_id, AssistantDocument.filename,
                  AssistantDocument.size_bytes, sa.func.length(AssistantDocument.content))
        .where(AssistantDocument.assistant_id.in_([a.id for a in assistenten]))
        .order_by(AssistantDocument.id)
    )).all()
    dokumente: dict[int, list[Dokument]] = {}
    for aid, name, groesse, laenge in zeilen:
        dokumente.setdefault(aid, []).append(Dokument(name, groesse, _token(laenge or 0)))

    ein, aus = REFERENZ_NACHRICHT
    ergebnis: dict[int, Kosten] = {}
    for a in assistenten:
        docs = dokumente.get(a.id, [])
        e = eigenschaften.get(modell_des_assistenten(a))
        if e is None or not e.preis_ein_usd:
            ergebnis[a.id] = Kosten(dokumente=docs)
            continue
        fest = _token(len(a.system_prompt or "") + len(bausteine_modul.texte(a.bausteine or [])))
        doc_token = sum(d.token for d in docs)
        ergebnis[a.id] = Kosten(
            usd_je_nachricht=(ein + fest + doc_token) * e.preis_ein_usd + aus * (e.preis_aus_usd or 0.0),
            usd_dokumente=doc_token * e.preis_ein_usd if docs else None,
            dokumente=docs,
        )
    return ergebnis
