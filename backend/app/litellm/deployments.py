"""Auflösung Deployment-Kennung → Anbietermodell (Modell-Transparenz).

**Wozu.** Gespeichert wird sonst nur der schulinterne Aliasname (`chat-standard`). Für eine
Quellenangabe in GFS, Seminarkurs oder Facharbeit ist der wertlos: Zitierfähig ist
`gpt-oss-120b`, nicht der Hausname. Die Zuordnung kennt allein die LiteLLM-Config.

**Warum über die Deployment-Kennung und nicht über den Alias.** LiteLLM gibt in jeder
Antwort den Header ``x-litellm-model-id`` zurück — einen Hash, der genau das Deployment
benennt, das die Anfrage bedient hat. Er entspricht ``model_info.id`` in ``/model/info``
(gemessen 28.08.2026) und führt damit auf ``litellm_params.model``. Das ist genauer als
eine Alias-Auflösung: Zeigt ein Alias auf mehrere Deployments (Lastverteilung, Fallback),
benennt der Alias nur die Gruppe — die Kennung das tatsächlich befragte Modell.

Was LiteLLM **nicht** liefert (ebenfalls gemessen): weder ``response.model`` noch
``x-litellm-model-group`` enthalten das Anbietermodell; beide geben den Alias zurück.

**Aufgelöst wird beim Schreiben, nicht bei der Anzeige.** Sonst änderte sich die Antwort
auf „womit wurde das erzeugt" rückwirkend, sobald jemand den Alias auf ein anderes Modell
umhängt — bei einer Facharbeit von vor drei Monaten genau das falsche Verhalten.
"""

from __future__ import annotations

import logging
import time

from app.litellm.client import LiteLLMClient

logger = logging.getLogger(__name__)

# Deployments ändern sich nur mit der Proxy-Config. Fünf Minuten sind reichlich; bei einer
# unbekannten Kennung wird ohnehin sofort neu geladen (siehe unten).
TTL_SEKUNDEN = 300.0

_client = LiteLLMClient()

# (Zeitpunkt, {deployment_id: anbietermodell}, {alias: anbietermodell})
_cache: tuple[float, dict[str, str], dict[str, str]] | None = None


def invalidate_deployment_cache() -> None:
    """Verwirft den Cache. Für Tests und nach Änderungen an der Proxy-Config."""
    global _cache
    _cache = None


async def _lade() -> tuple[dict[str, str], dict[str, str]]:
    """Holt `/model/info` und baut beide Zuordnungen. Bei Fehler: leer."""
    global _cache
    try:
        eintraege = await _client.get_model_deployments()
    except Exception:
        logger.warning("Deployment-Zuordnung nicht abrufbar", exc_info=True)
        return {}, {}

    nach_id: dict[str, str] = {}
    nach_alias: dict[str, str] = {}
    for e in eintraege:
        ziel = str((e.get("litellm_params") or {}).get("model") or "").strip()
        if not ziel:
            continue
        kennung = (e.get("model_info") or {}).get("id")
        if kennung:
            nach_id[str(kennung)] = ziel
        alias = e.get("model_name")
        # Erster Treffer gewinnt: Bei mehreren Deployments je Alias ist die Zuordnung
        # ohnehin mehrdeutig — dafür gibt es die Kennung.
        if alias and alias not in nach_alias:
            nach_alias[alias] = ziel

    _cache = (time.monotonic(), nach_id, nach_alias)
    return nach_id, nach_alias


async def _zuordnungen(erzwinge_neu: bool = False) -> tuple[dict[str, str], dict[str, str]]:
    if not erzwinge_neu and _cache is not None and time.monotonic() - _cache[0] < TTL_SEKUNDEN:
        return _cache[1], _cache[2]
    return await _lade()


async def anbietermodell(
    deployment_id: str | None, alias: str | None = None
) -> str | None:
    """Anbietermodell (z. B. ``openai/openai/gpt-oss-120b``) oder None.

    Bevorzugt die Deployment-Kennung aus ``x-litellm-model-id``; fehlt sie (ältere
    LiteLLM-Version, Antwort ohne Header), wird über den Alias aufgelöst.

    Eine unbekannte Kennung löst **einen** sofortigen Neuabruf aus: Ein gerade
    hinzugefügtes Modell wäre sonst bis zum Ablauf der TTL nicht auflösbar, und die
    Herkunft eines Bildes lässt sich später nicht nachtragen.

    Gibt None zurück, wenn nichts zu ermitteln war — das heißt **unbekannt**, nicht
    „kein Modell". Aufrufer speichern dann nur den Alias.
    """
    if not deployment_id and not alias:
        return None

    nach_id, nach_alias = await _zuordnungen()
    if deployment_id and deployment_id in nach_id:
        return nach_id[deployment_id]
    if deployment_id:
        nach_id, nach_alias = await _zuordnungen(erzwinge_neu=True)
        if deployment_id in nach_id:
            return nach_id[deployment_id]
        logger.info(
            "Deployment-Kennung %s nicht auflösbar — Alias '%s' als Rückfall.",
            deployment_id, alias,
        )
    if alias and alias in nach_alias:
        return nach_alias[alias]
    return None


def zitiername(anbieter_modell: str | None) -> str | None:
    """Anbietermodell → der Name, den man in eine Quellenangabe schreibt.

    ``openai/openai/gpt-oss-120b`` → ``gpt-oss-120b``,
    ``mistral/mistral-small-latest`` → ``mistral-small-latest``,
    ``anthropic/claude-sonnet-5`` → ``claude-sonnet-5``.

    Das Provider-Präfix ist LiteLLM-Syntax und gehört nicht in eine Quellenangabe; der
    Anbieter selbst wird getrennt genannt. Der **letzte** Pfadteil ist der Modellname —
    bei IONOS steht davor sowohl das LiteLLM-Provider-Präfix als auch der Herausgeber
    (``openai/openai/gpt-oss-120b``).
    """
    if not anbieter_modell:
        return None
    return anbieter_modell.rstrip("/").rsplit("/", 1)[-1] or None
