"""Zwischengespeicherte Sicht auf die Modell-Freigaben je Team (Mehrmodell-Plan, Schritt 5).

**Wozu.** Das Werkzeug-Schema soll einer Schülerin nur Bildarten anbieten, deren Modell für
ihren Jahrgang überhaupt freigeschaltet ist. Sonst wählt das Chat-Modell eine gesperrte
Bildart, der Proxy antwortet mit 403 und im Gespräch steht ein Fehler, den niemand
auflösen kann — am wenigsten die Schülerin.

**Warum ein Cache.** Die Zuordnung Nutzer:in → Team ist lokal ableitbar
(``teams.get_target_team_id``, Rolle + Jahrgang). Nur „welche Modelle hat Team X" muss beim
Proxy erfragt werden, und das ändert sich selten — eine Freigabe setzt ein Mensch von Hand.
Ein Roundtrip pro Chat-Anfrage wäre reine Verschwendung und ein zusätzlicher Grund, warum
ein Chat langsam wird.

**Warum der Cache nie zur Ausfallquelle wird.** Ist der Proxy nicht erreichbar, liefert
dieses Modul ``None`` — „unbekannt", nicht „nichts erlaubt". Der Aufrufer filtert dann
nicht. Das ist Absicht: Der Filter ist Ergonomie, die **Durchsetzung** bleibt beim Proxy,
der jede unerlaubte Anfrage ohnehin abweist. Ein Filter, der bei einer Störung alles
wegnimmt, machte aus einem Anzeigeproblem einen Totalausfall.
"""

from __future__ import annotations

import logging
import time

from app.litellm.client import LiteLLMClient

logger = logging.getLogger(__name__)

# Freigaben ändert ein Mensch von Hand; fünf Minuten Verzögerung sind unkritisch und
# sparen einen Proxy-Roundtrip je Chat-Anfrage.
TTL_SEKUNDEN = 300.0

# LiteLLMs Platzhalter für „nichts freigeschaltet" — keine Modell-ID.
_NO_DEFAULT = ["no-default-models"]

_client = LiteLLMClient()

# team_id → (Zeitpunkt, Modelle). Bewusst prozesslokal: Bei mehreren Arbeitsprozessen hält
# jeder seinen eigenen Stand, was höchstens bedeutet, dass eine frische Freigabe ein paar
# Minuten uneinheitlich sichtbar ist. Ein geteilter Cache wäre dafür zu viel Apparat.
_cache: dict[str, tuple[float, set[str]]] = {}


def invalidate_team_models_cache(team_id: str | None = None) -> None:
    """Verwirft den Cache — ganz oder für ein Team. Für Tests und nach Freigabeänderungen."""
    if team_id is None:
        _cache.clear()
    else:
        _cache.pop(team_id, None)


async def erlaubte_modelle(team_id: str) -> set[str] | None:
    """Freigeschaltete Modelle des Teams, oder ``None``, wenn es nicht zu erfahren war.

    ``None`` heißt ausdrücklich **unbekannt**, nicht „leer": Der Aufrufer soll dann nicht
    filtern. Ein leeres Set dagegen heißt „für dieses Team ist wirklich nichts frei".
    """
    jetzt = time.monotonic()
    eintrag = _cache.get(team_id)
    if eintrag is not None and jetzt - eintrag[0] < TTL_SEKUNDEN:
        return eintrag[1]

    try:
        info = await _client.get_team_info(team_id)
    except Exception:
        logger.warning(
            "Modell-Freigaben für Team '%s' nicht abrufbar — es wird nicht gefiltert.",
            team_id, exc_info=True,
        )
        return None

    if info is None:
        # 404: Das Team gibt es (noch) nicht. Auch das ist „unbekannt" und kein Grund,
        # der Nutzerin sämtliche Bildarten zu verbergen.
        logger.info("Team '%s' im Proxy nicht vorhanden — es wird nicht gefiltert.", team_id)
        return None

    modelle = info.get("models") or []
    if modelle == _NO_DEFAULT:
        modelle = []
    ergebnis = set(modelle)
    _cache[team_id] = (jetzt, ergebnis)
    return ergebnis


async def erlaubte_modelle_fuer(roles: list[str], grade: int | str | None) -> set[str] | None:
    """Wie ``erlaubte_modelle``, aber ausgehend von Rolle und Jahrgang.

    Lässt sich kein Team ableiten (Rolle ohne Team, Schüler:in ohne gültigen Jahrgang),
    ist das ebenfalls „unbekannt" — nicht „nichts erlaubt".
    """
    from app.litellm.teams import get_target_team_id

    try:
        team_id = get_target_team_id(roles, grade)
    except ValueError:
        logger.debug("Kein Zielteam für roles=%s grade=%r — es wird nicht gefiltert.",
                     roles, grade)
        return None
    return await erlaubte_modelle(team_id)
