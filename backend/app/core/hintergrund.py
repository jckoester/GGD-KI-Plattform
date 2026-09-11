"""Aufgaben, die nach der Antwort weiterlaufen.

Zwei Dinge geschehen in dieser Anwendung, nachdem die Antwort beim Nutzer ist: Die
Kosten werden nachgetragen (LiteLLM schreibt seine SpendLogs verzögert) und bei
einem Krisenfall wird benachrichtigt (ein Mailserver darf keinen Chat aufhalten).
Beide brauchen dasselbe Gerüst.

⚠️ **Drei Fallen, alle drei still:**

* *Die Sitzung des Requests ist zu.* Wenn die Aufgabe läuft, hat FastAPI sie längst
  geschlossen. Jede Aufgabe öffnet ihre eigene.
* *Eine Aufgabe ohne Referenz verschwindet.* `asyncio.create_task` allein genügt
  nicht; ohne festgehaltene Referenz darf der Garbage Collector sie einsammeln.
  Deshalb :data:`_OFFEN`.
* *Ein Neustart verlöre die laufenden.* Deshalb wartet das Herunterfahren kurz
  (:func:`warte_auf_abschluss`).
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

# Starke Referenzen auf die laufenden Aufgaben — siehe Modulkopf.
_OFFEN: set[asyncio.Task] = set()

# Wie lange das Herunterfahren wartet. Länger hielte einen Neustart auf, kürzer
# verlöre die meisten gerade laufenden Aufgaben.
ABSCHLUSSFRIST = 5.0


def offene_anzahl() -> int:
    """Wie viele Aufgaben gerade laufen — für Diagnose und Tests."""
    return len(_OFFEN)


def im_hintergrund(coro_fabrik, *, was: str) -> asyncio.Task:
    """Startet eine Aufgabe, hält sie fest und protokolliert ihre Fehler.

    Fehler landen im Log, nicht beim Nutzer: Der Vorgang, der sie ausgelöst hat, ist
    an dieser Stelle abgeschlossen.
    """
    async def _sicher():
        try:
            await coro_fabrik()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("%s fehlgeschlagen", was)

    aufgabe = asyncio.create_task(_sicher())
    _OFFEN.add(aufgabe)
    aufgabe.add_done_callback(_OFFEN.discard)
    return aufgabe


async def warte_auf_abschluss(frist: float = ABSCHLUSSFRIST) -> None:
    """Beim Herunterfahren: laufende Aufgaben zu Ende bringen lassen.

    Was die Frist nicht schafft, geht verloren. Bei den Kosten bleibt die Nachricht
    dann auf `ausstehend` stehen — die ehrlichere Spur als ein Betrag, der nie kam,
    sich aber wie ein endgültiger liest.
    """
    if not _OFFEN:
        return
    logger.info("Warte auf %d offene Hintergrundaufgaben…", len(_OFFEN))
    _, offen = await asyncio.wait(set(_OFFEN), timeout=frist)
    if offen:
        logger.warning(
            "%d Hintergrundaufgaben beim Herunterfahren abgebrochen.", len(offen)
        )
        for aufgabe in offen:
            aufgabe.cancel()
