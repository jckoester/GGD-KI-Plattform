"""Benachrichtigung über neue Meldungen — Platzhalter, gefüllt in AP3 (ADR-020).

Die Aufrufstelle steht schon in `service.erstelle`, damit AP3 nur den Rumpf hier
auswechseln muss und nicht den Chat-Pfad noch einmal anfasst. Bis dahin passiert
nichts: `FEEDBACK_NOTIFY_TO`, Dämpfung über das Stundenfenster und der Mailtext
gehören in dasselbe Arbeitspaket wie die Admin-Sicht, auf die die Mail verweist.
"""
import logging

logger = logging.getLogger(__name__)


async def benachrichtige(session_factory, *, sender=None, jetzt=None) -> bool:
    """Noch ohne Wirkung. Signatur wie `app.crisis.benachrichtigung.benachrichtige`.

    :returns: ob versendet wurde — bis AP3 immer `False`.
    """
    return False
