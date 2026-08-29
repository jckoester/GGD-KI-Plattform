"""Fehlerantworten des LiteLLM-Proxys deuten.

**Der HTTP-Status trägt die Auskunft nicht.** LiteLLM 1.83.7 meldet ein aufgebrauchtes
Budget mit **HTTP 400** und ``type: budget_exceeded`` (gemessen 29.08.2026):

    {"error":{"message":"Budget has been exceeded! Current cost: 2.6e-05,
     Max budget: 2e-05","type":"budget_exceeded","code":"400"}}

Ältere Fassungen antworteten mit 429, und der Status kann sich mit jeder LiteLLM-Version
wieder ändern. Umgekehrt ist ein 429 **nicht** zwingend ein Budgetproblem: Es kann die
eigene Drossel aus ``rate_limits.yaml`` sein oder die Ratenbegrenzung des Anbieters.

Wer auf den Status prüft, verwechselt also beides — in beide Richtungen. Genau das ist
passiert: Die Oberfläche zeigte bei jedem 429 „Dein Budget ist erschöpft", auch bei einer
reinen Drosselung, und beim echten Budgetende (400) gar nichts Passendes.

Deshalb entscheidet hier der **Fehlertyp im Antwortkörper**, nicht der Status.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Der Typ, den LiteLLM bei erschöpftem Budget setzt — an Schlüssel *und* Team.
BUDGET_TYP = "budget_exceeded"


def _als_text(body: Any) -> str:
    if body is None:
        return ""
    if isinstance(body, (bytes, bytearray)):
        return body.decode("utf-8", errors="replace")
    return str(body)


def ist_budget_erschoepft(body: Any) -> bool:
    """Meldet dieser Fehlerkörper ein aufgebrauchtes Budget?

    Erst strukturiert (``error.type``), dann als Textsuche. Die Textsuche ist kein
    Schnellschuss, sondern der Rückfall für den Fall, dass LiteLLM die Hülle umbaut: Der
    Typname selbst ist über die Versionen stabil geblieben, die Verschachtelung nicht.

    Ein falsch positiver Treffer wäre harmlos (eine unpassende, aber freundliche Meldung);
    ein falsch negativer führt zurück in den Zustand, den diese Funktion behebt.
    """
    text = _als_text(body)
    if not text:
        return False

    try:
        daten = json.loads(text)
    except (ValueError, TypeError):
        daten = None

    if isinstance(daten, dict):
        fehler = daten.get("error")
        if isinstance(fehler, dict) and str(fehler.get("type", "")) == BUDGET_TYP:
            return True
        # Manche Pfade liefern den Typ flach statt unter `error`.
        if str(daten.get("type", "")) == BUDGET_TYP:
            return True

    return BUDGET_TYP in text


#: Was Nutzer:innen bei erschöpftem Budget lesen. Bewusst ohne Zahlen: Der Betrag steht
#: im Profil, und „Current cost: 2.6e-05" hilft niemandem weiter.
BUDGET_MELDUNG = (
    "Dein Budget für diesen Zeitraum ist aufgebraucht. "
    "Es wird zum nächsten Abrechnungszeitraum wieder aufgefüllt — "
    "deine bisherigen Chats bleiben erhalten."
)
