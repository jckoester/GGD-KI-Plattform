"""LiteLLM-Custom-Guardrail: Jugendschutz per LLM-Klassifikator.

Ersatz für die drei `openai_moderation`-Guardrails (`explicit_sexual_content`,
`graphic_violence`, `self_harm_instructions`) — EU-Anbieter wie IONOS haben keine
Moderation-API (ADR-015 §6).

**Deployment:** Diese Datei muss dort liegen, wo der LiteLLM-Proxy läuft, und von seinem
Arbeitsverzeichnis aus importierbar sein. Der Proxy läuft NICHT in `docker-compose.yml` —
lokal in `infra/litellm-venv`, in Produktion auf dem Proxy-Host.

Konfiguration (siehe `infra/litellm_config.ionos.example.yaml`):

    guardrails:
      - guardrail_name: "jugendschutz"
        litellm_params:
          guardrail: llm_moderation.LlmModerationGuardrail
          mode: post_call
          default_on: true
          classifier_model: openai/gpt-4o-mini   # oder ein IONOS-Modell
          classifier_api_base: os.environ/IONOS_API_BASE
          classifier_api_key: os.environ/IONOS_API_KEY
          timeout: 8.0
          thresholds:
            sexual: 0.5
            violence_graphic: 0.7
            self_harm_instructions: 0.5

**Fail-open.** Timeout, Netzfehler oder eine unlesbare Klassifikator-Antwort lassen den Text
durch und schreiben eine Warnung ins Log. Begründung: Ein fail-closed Guardrail würde bei
einer Anbieterstörung die gesamte Plattform blockieren — für alle Fächer, den ganzen Tag.
Das steht in keinem Verhältnis zum Risiko, das er abwehrt, und ist konsistent mit dem
PII-Gate (Phase 14) und ADR-008 Teil 3.

**Kostenhinweis:** Der Klassifikator-Aufruf läuft nicht über den Virtual Key der
Nutzer:innen, sondern über den hier konfigurierten Zugang — sein Spend erscheint also nicht
im Nutzerbudget. Bei `default_on: true` fällt er bei JEDER Antwort an; ein kleines, günstiges
Modell wählen.
"""

import json
import logging
import os
from typing import Any, Optional

import litellm
from litellm.integrations.custom_guardrail import CustomGuardrail
from litellm.proxy._types import UserAPIKeyAuth

from moderation_core import (
    DEFAULT_CATEGORIES,
    build_messages,
    parse_scores,
    violated_categories,
)

logger = logging.getLogger("litellm.guardrails.llm_moderation")


def _resolve(value: Optional[str]) -> Optional[str]:
    """Löst `os.environ/NAME` auf — LiteLLM tut das für eigene Felder, nicht für unsere."""
    if isinstance(value, str) and value.startswith("os.environ/"):
        return os.environ.get(value.split("/", 1)[1])
    return value


class LlmModerationGuardrail(CustomGuardrail):
    def __init__(self, **kwargs: Any) -> None:
        self.classifier_model = kwargs.pop("classifier_model", None)
        self.classifier_api_base = _resolve(kwargs.pop("classifier_api_base", None))
        self.classifier_api_key = _resolve(kwargs.pop("classifier_api_key", None))
        self.timeout = float(kwargs.pop("timeout", 8.0))
        self.thresholds = kwargs.pop("thresholds", None) or {}
        super().__init__(**kwargs)
        if not self.classifier_model:
            logger.error(
                "LlmModerationGuardrail ohne `classifier_model` konfiguriert — der Guardrail "
                "lässt damit ALLES durch. Modell in der LiteLLM-Config eintragen."
            )

    async def _classify(self, text: str) -> Optional[dict[str, float]]:
        """Fragt den Klassifikator. None = kein belastbares Urteil (→ durchlassen)."""
        if not self.classifier_model or not text.strip():
            return None
        try:
            response = await litellm.acompletion(
                model=self.classifier_model,
                messages=build_messages(text),
                api_base=self.classifier_api_base,
                api_key=self.classifier_api_key,
                timeout=self.timeout,
                temperature=0,
                max_tokens=200,
            )
            raw = response["choices"][0]["message"]["content"]
        except Exception as exc:
            logger.warning(
                "Moderations-Klassifikator nicht erreichbar (%s: %s) — Antwort wird "
                "durchgelassen (fail-open).", type(exc).__name__, exc,
            )
            return None

        scores = parse_scores(raw)
        if scores is None:
            logger.warning(
                "Moderations-Klassifikator lieferte keine auswertbare Antwort (%r) — "
                "Antwort wird durchgelassen (fail-open).", str(raw)[:200],
            )
        return scores

    async def async_post_call_success_hook(
        self, data: dict, user_api_key_dict: UserAPIKeyAuth, response: Any
    ) -> Any:
        text = _response_text(response)
        if not text:
            return response

        scores = await self._classify(text)
        if scores is None:
            return response  # fail-open, bereits geloggt

        hits = violated_categories(scores, DEFAULT_CATEGORIES, self.thresholds)
        if not hits:
            return response

        # Bewusst ohne den Antworttext im Log: Der Verstoß ist protokolliert, der Inhalt
        # bleibt draußen (Datenschutz-Invariante — Logs sind kein Ort für Chat-Inhalte).
        logger.warning(
            "Antwort blockiert. Kategorien: %s. Werte: %s",
            ", ".join(hits), json.dumps(scores, sort_keys=True),
        )
        raise ValueError(
            "Diese Antwort wurde vom Jugendschutz-Filter der Schule zurückgehalten."
        )


def _response_text(response: Any) -> str:
    """Extrahiert den Antworttext; leer, wenn es keinen gibt (z. B. reiner Tool-Call)."""
    try:
        choices = response["choices"] if isinstance(response, dict) else response.choices
        parts = []
        for choice in choices:
            message = choice["message"] if isinstance(choice, dict) else choice.message
            content = message.get("content") if isinstance(message, dict) else message.content
            if content:
                parts.append(str(content))
        return "\n".join(parts)
    except Exception:
        return ""
