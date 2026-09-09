"""Kosten eines Chat-Zuges nachtragen — nach dem Antworttext, nicht davor.

**Warum.** LiteLLM schreibt die SpendLogs verzögert. Bis 09/2026 wartete der Chat
darauf **im Stream**: gestaffelt 1 s, 3 s, 7 s, bis zu 15 s, nachdem das letzte
Zeichen der Antwort längst dastand. In dieser Zeit hing die Verbindung, der
Absenden-Knopf blieb gesperrt, und die Oberfläche zeigte einen fertigen Text im
laufenden Zustand — für eine Randnotiz unter der Blase.

Jetzt endet der Stream, sobald die Antwort steht. Die Kosten holt eine Aufgabe
hinterher und schreibt sie nach.

**Was dabei nicht auf dem Spiel steht:** Die Budgetgrenze zieht LiteLLM am Virtual
Key, nicht diese Datenbank. Ein später geschriebener Betrag verändert **keine**
Freigabeentscheidung — er betrifft Anzeige und Statistik.

⚠️ **Drei Fallen, alle drei still:**

* *Die Sitzung des Requests ist zu.* Wenn die Aufgabe läuft, hat FastAPI die
  Request-Sitzung längst geschlossen. Die Aufgabe öffnet eine eigene.
* *Eine Aufgabe ohne Referenz verschwindet.* `asyncio.create_task` allein genügt
  nicht; ohne festgehaltene Referenz darf der Garbage Collector sie einsammeln.
  Deshalb `_OFFEN`.
* *Ein Neustart verlöre die laufenden Züge.* Deshalb wartet das Herunterfahren
  kurz (:func:`warte_auf_abschluss`).
"""
import asyncio
import logging
from uuid import UUID

import sqlalchemy as sa

logger = logging.getLogger(__name__)

# Starke Referenzen auf die laufenden Aufgaben — siehe Modulkopf.
_OFFEN: set[asyncio.Task] = set()

# Wie lange das Herunterfahren auf offene Nachträge wartet. Länger hielte einen
# Neustart auf, kürzer verlöre die meisten gerade laufenden Züge.
ABSCHLUSSFRIST = 5.0


def offene_anzahl() -> int:
    """Wie viele Nachträge gerade laufen — für Diagnose und Tests."""
    return len(_OFFEN)


async def _schreibe(session_factory, message_id: UUID, conversation_id: UUID,
                    betrag: float | None, zustand: str) -> None:
    """Betrag und Zustand an Nachricht und Konversation nachtragen.

    Der Betrag wird **addiert**, nicht gesetzt: An der Nachricht können bereits
    exakte Bildkosten stehen, die beim Schreiben schon bekannt waren.
    """
    from app.db.models import Conversation, Message

    async with session_factory() as db:
        werte: dict = {"cost_status": zustand}
        if betrag is not None:
            werte["cost_usd"] = sa.func.coalesce(Message.cost_usd, 0) + betrag
        await db.execute(
            sa.update(Message).where(Message.id == message_id).values(**werte)
        )
        if betrag is not None:
            await db.execute(
                sa.update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(
                    total_cost_usd=sa.func.coalesce(Conversation.total_cost_usd, 0)
                    + betrag
                )
            )
        await db.commit()


async def _lauf(session_factory, message_id: UUID, conversation_id: UUID,
                request_ids: list[str], wartezeiten: tuple[float, ...]) -> None:
    from app.chat.router import _kosten_des_zuges
    from app.litellm.client import LiteLLMClient

    client = LiteLLMClient()
    try:
        kosten = await _kosten_des_zuges(
            client, request_ids, wartezeiten=wartezeiten
        )
    finally:
        await client.close()

    await _schreibe(
        session_factory, message_id, conversation_id, kosten.summe, kosten.zustand
    )
    logger.info(
        "Kosten nachgetragen für Nachricht %s: %d von %d Anfragen, Summe %s (%s)",
        message_id, kosten.gefunden, kosten.gesamt,
        "—" if kosten.summe is None else f"{kosten.summe:.6f}", kosten.zustand,
    )


def nachtragen(session_factory, *, message_id: UUID, conversation_id: UUID,
               request_ids: list[str], wartezeiten: tuple[float, ...]) -> asyncio.Task:
    """Startet den Nachtrag und gibt die Aufgabe zurück (für Tests).

    Fehler landen im Log, nicht beim Nutzer: Der Chat ist an dieser Stelle fertig,
    und eine fehlende Kostenangabe ist kein Grund, ihn nachträglich zu stören. Der
    Zustand bleibt dann `ausstehend` — sichtbar als „wird ermittelt", statt als
    stille Null.
    """
    async def _sicher():
        try:
            await _lauf(session_factory, message_id, conversation_id,
                        request_ids, wartezeiten)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Kosten-Nachtrag für Nachricht %s fehlgeschlagen", message_id)

    aufgabe = asyncio.create_task(_sicher())
    _OFFEN.add(aufgabe)
    aufgabe.add_done_callback(_OFFEN.discard)
    return aufgabe


async def warte_auf_abschluss(frist: float = ABSCHLUSSFRIST) -> None:
    """Beim Herunterfahren: offene Nachträge zu Ende bringen lassen.

    Was die Frist nicht schafft, geht verloren — dann bleibt die Nachricht auf
    `ausstehend` stehen. Das ist die ehrlichere Spur als ein Betrag, der nie kam,
    sich aber wie ein endgültiger liest.
    """
    if not _OFFEN:
        return
    logger.info("Warte auf %d offene Kosten-Nachträge…", len(_OFFEN))
    erledigt, offen = await asyncio.wait(set(_OFFEN), timeout=frist)
    if offen:
        logger.warning(
            "%d Kosten-Nachträge beim Herunterfahren abgebrochen — die Nachrichten "
            "bleiben auf 'ausstehend'.", len(offen),
        )
        for aufgabe in offen:
            aufgabe.cancel()
