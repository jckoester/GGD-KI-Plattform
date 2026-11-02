"""Der Chat-Anhang einer Meldung — eine Kopie, kein Verweis (ADR-020).

**Warum kopiert wird.** Ein Verweis auf `conversations.id` zeigte ins Leere, sobald die
Konversation nach 90 Tagen (ADR-011) oder durch die Person selbst verschwindet — und
genau dann braucht die Sichtung den Inhalt noch. Der Snapshot hängt deshalb an der
Frist der Meldung, nicht an der des Chats. Das Formular benennt diese Verlängerung.

**Was nicht mitkommt:** Kosten und Token-Zahlen. Sie beantworten keine Frage, die eine
Fehlermeldung stellt, und machten aus dem Anhang eine Abrechnungsspur.

Formung und Abfrage sind getrennt: `baue` rechnet auf gewöhnlichen Objekten und ist
ohne Datenbank prüfbar, `lade` holt die Zeilen und prüft das Eigentum.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NACHRICHTEN_FOLGE, Conversation, Message

# Genug, um einen Fehler im Verlauf zu verstehen; wenig genug, dass der Anhang kein
# Zweitarchiv der Chathistorie wird.
GEKUERZT_AUF = 50


def _in_der_vorschau_verborgen(konversation, pseudonym: str) -> bool:
    """In der Vorschau (0.29) sind nur Vorschau-Chats erreichbar — auch für den Anhang."""
    from app.auth.vorschau import aktive

    return aktive(pseudonym) is not None and konversation.preview_context is None


def baue(konversation, nachrichten) -> dict:
    """Der JSONB-Inhalt. `created_at` als ISO-Zeichenkette — JSONB kennt kein datetime."""
    return {
        "conversation_id": str(konversation.id),
        "assistant_id": konversation.assistant_id,
        "model_used": konversation.model_used,
        "title": konversation.title,
        "messages": [
            {
                "role": n.role,
                "content": n.content,
                "model": n.model,
                "provider_model": n.provider_model,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in nachrichten
        ],
    }


async def lade(db: AsyncSession, conversation_id: UUID, pseudonym: str) -> dict | None:
    """Der Snapshot einer **eigenen** Konversation, sonst `None`.

    Fremd und nicht vorhanden geben denselben Wert zurück, und der Router macht daraus
    dieselbe 404: Ein 403 auf eine fremde Konversation verriete, dass es sie gibt.
    """
    konversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.pseudonym == pseudonym,
        )
    )
    if konversation is None or _in_der_vorschau_verborgen(konversation, pseudonym):
        return None

    # Alle Zeilen holen und in Python schneiden, statt `ORDER BY … DESC LIMIT 50`:
    # `now()` ist in PostgreSQL die **Transaktionszeit**, zwei im selben Zug
    # geschriebene Nachrichten tragen denselben Zeitstempel. Ein `LIMIT` auf einer
    # mehrdeutigen Sortierung schnitte dann willkürlich mitten in ein Paar. Eine
    # Konversation hat höchstens einige hundert Zeilen — das trägt. Die Sortierung
    # selbst ist seit 07.10.2026 eindeutig (`NACHRICHTEN_FOLGE`).
    ergebnis = await db.execute(
        select(Message)
        # Was die Person sieht: ohne ersetzte Nachrichten (0.19).
        .where(Message.conversation_id == conversation_id, Message.ersetzt_am.is_(None))
        .order_by(*NACHRICHTEN_FOLGE)
    )
    nachrichten = list(ergebnis.scalars().all())[-GEKUERZT_AUF:]
    return baue(konversation, nachrichten)


async def modell(
    db: AsyncSession, conversation_id: UUID, pseudonym: str
) -> tuple[str | None, str | None]:
    """Alias und Anbietermodell der letzten Antwort einer **eigenen** Konversation (0.28.1).

    Ohne Antwort mit Modell gilt das Modell der Konversation (Alias, ohne Anbietermodell).
    Fremd oder unbekannt: `(None, None)` — die Meldung geht trotzdem durch; anders als beim
    Anhang ist das Modell eine Beigabe, kein Wunsch der meldenden Person.
    """
    konversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.pseudonym == pseudonym,
        )
    )
    if konversation is None or _in_der_vorschau_verborgen(konversation, pseudonym):
        return None, None
    # Aufsteigend nach `NACHRICHTEN_FOLGE` und in Python die letzte, wie in `lade` — ein
    # `DESC LIMIT 1` auf dem Zeitstempel wäre bei gleichen Zeitpunkten mehrdeutig.
    antworten = (await db.execute(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.role == "assistant",
            Message.model.is_not(None),
            Message.ersetzt_am.is_(None),
        )
        .order_by(*NACHRICHTEN_FOLGE)
    )).scalars().all()
    letzte = antworten[-1] if antworten else None
    if letzte is not None:
        return letzte.model, letzte.provider_model
    return konversation.model_used, None
