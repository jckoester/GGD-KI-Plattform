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

**Verhalten bei Ausfall — publikumsabhängig.** Reine Fail-open-Politik wäre zu riskant: Auf
der Ausgabeseite ist dieser Guardrail die einzige Prüfung (die lokale Krisenerkennung im
Backend scannt die *Eingabe* und blockiert nach ADR-008 Teil 3 bewusst nicht). Reines
fail-closed wäre es ebenso: Eine Anbieterstörung legte den Unterricht der ganzen Schule lahm.

Deshalb gestaffelt — Wiederholung, dann optionaler Rückfall-Klassifikator, und wenn beides
nichts liefert, entscheidet das Team: **Lehrkräfte** arbeiten weiter, **Schüler:innen**
werden blockiert (`fail_open_teams`, Vorgabe `{"lehrkraefte"}`). Ein unbekanntes Team gilt
als schutzbedürftig.

**Zählerstand.** Fail-open ist nur zu verantworten, wenn man weiß, wie oft es eintritt.
Über `health_file` legt der Guardrail einen JSON-Zustandsbericht ab, den das Backend unter
`/admin/guardrail/health` ausliefert. Ein Monitoring sollte ihn abfragen und daran eine
Benachrichtigung hängen — die Plattform selbst verschickt keine Mails.

**Kostenhinweis:** Der Klassifikator-Aufruf läuft nicht über den Virtual Key der
Nutzer:innen, sondern über den hier konfigurierten Zugang — sein Spend erscheint also nicht
im Nutzerbudget. Bei `default_on: true` fällt er bei JEDER Antwort an; ein kleines, günstiges
Modell wählen.
"""

import json
import logging
import os
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import litellm
from litellm.integrations.custom_guardrail import CustomGuardrail
from litellm.proxy._types import UserAPIKeyAuth

from moderation_core import (
    DEFAULT_CATEGORIES,
    build_messages,
    build_health_snapshot,
    fail_closed,
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
        # Ein zweiter Anlauf deckt die häufigste Störung ab — die kurze. Er ist bewusst
        # der Standard: Der Klassifikator läuft ohnehin nur bei einer Antwort, und ein
        # zusätzlicher Aufruf im Fehlerfall wiegt leichter als eine unnötige Blockade.
        self.retries = int(kwargs.pop("classifier_retries", 1))

        # Optionaler zweiter Klassifikator (Entscheidung der Schule). Zwei Spielarten:
        #   · gleiches Modell bei einem ANDEREN Anbieter → echte Ausfallsicherheit, ohne
        #     dass die Abgrenzung gegen Unterrichtstexte neu geprüft werden muss;
        #   · ein anderes Modell → braucht dieselbe Prüfung wie das primäre, sonst tauscht
        #     man im Störfall eine bekannte Größe gegen eine unbekannte.
        self.fallback_model = kwargs.pop("fallback_classifier_model", None)
        self.fallback_api_base = _resolve(kwargs.pop("fallback_classifier_api_base", None))
        self.fallback_api_key = _resolve(kwargs.pop("fallback_classifier_api_key", None))

        self.timeout = float(kwargs.pop("timeout", 8.0))
        self.thresholds = kwargs.pop("thresholds", None) or {}
        fail_open_teams = kwargs.pop("fail_open_teams", None)
        self.fail_open_teams = set(fail_open_teams) if fail_open_teams is not None else None
        self.health_file = kwargs.pop("health_file", None)

        self._counters: Counter = Counter()
        super().__init__(**kwargs)
        if not self.classifier_model:
            logger.error(
                "LlmModerationGuardrail ohne `classifier_model` konfiguriert — der Guardrail "
                "lässt damit ALLES durch. Modell in der LiteLLM-Config eintragen."
            )

    # ── Zustandsbericht ──────────────────────────────────────────────────────

    def _write_health(self) -> None:
        """Schreibt den Zählerstand als JSON, damit das Backend ihn ausliefern kann.

        Atomar über eine temporäre Datei: Das Backend liest die Datei nebenläufig, und
        ein halb geschriebener Stand wäre nicht parsebar. Fehler hier dürfen den Guardrail
        NIE beeinträchtigen — Buchhaltung ist kein Grund, eine Antwort zu blockieren.
        """
        if not self.health_file:
            return
        try:
            snapshot = build_health_snapshot(
                dict(self._counters),
                classifier=self.classifier_model,
                fallback=self.fallback_model,
                zeitstempel=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
            ziel = Path(self.health_file)
            ziel.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=ziel.parent, delete=False
            ) as f:
                json.dump(snapshot, f, ensure_ascii=False)
                temp = Path(f.name)
            temp.replace(ziel)
        except Exception as exc:  # pragma: no cover — reine Absicherung
            logger.debug("Guardrail-Zustandsbericht nicht schreibbar: %s", exc)

    # ── Klassifikation ───────────────────────────────────────────────────────

    async def _ask(self, text: str, *, model: str, api_base: Optional[str],
                   api_key: Optional[str]) -> Optional[dict[str, float]]:
        """Ein Aufruf. None = kein Urteil (Fehler oder unlesbare Antwort)."""
        try:
            response = await litellm.acompletion(
                model=model,
                messages=build_messages(text),
                api_base=api_base,
                api_key=api_key,
                timeout=self.timeout,
                temperature=0,
                max_tokens=200,
            )
            raw = response["choices"][0]["message"]["content"]
        except Exception as exc:
            logger.warning("Moderations-Klassifikator '%s' nicht erreichbar (%s: %s).",
                           model, type(exc).__name__, exc)
            return None

        scores = parse_scores(raw)
        if scores is None:
            logger.warning("Moderations-Klassifikator '%s' lieferte keine auswertbare "
                           "Antwort (%r).", model, str(raw)[:200])
        return scores

    async def _classify(self, text: str) -> Optional[dict[str, float]]:
        """Primär, dann Wiederholung, dann optionaler Rückfall. None = kein Urteil."""
        if not self.classifier_model or not text.strip():
            return None

        for versuch in range(self.retries + 1):
            scores = await self._ask(
                text, model=self.classifier_model,
                api_base=self.classifier_api_base, api_key=self.classifier_api_key,
            )
            if scores is not None:
                if versuch == 0:
                    self._counters["primary_ok"] += 1
                else:
                    self._counters["retry_ok"] += 1
                    # Bewusst WARNING, nicht DEBUG: Häufige, aber gelungene Wiederholungen
                    # haben andere Ursachen als vollständige Ausfälle (Latenz, Überlast,
                    # zu knappes Timeout) und wären in einer Erfolgsquote unsichtbar.
                    logger.warning(
                        "Moderations-Klassifikator erst im %d. Versuch erfolgreich — "
                        "häufen sich diese Meldungen, ist das Timeout (%.1fs) zu knapp "
                        "oder der Anbieter überlastet.", versuch + 1, self.timeout,
                    )
                return scores

        if self.fallback_model:
            scores = await self._ask(
                text, model=self.fallback_model,
                api_base=self.fallback_api_base, api_key=self.fallback_api_key,
            )
            if scores is not None:
                self._counters["fallback_ok"] += 1
                logger.warning(
                    "Primärer Moderations-Klassifikator ausgefallen — Rückfall auf '%s'.",
                    self.fallback_model,
                )
                return scores
        return None

    async def async_post_call_success_hook(
        self, data: dict, user_api_key_dict: UserAPIKeyAuth, response: Any
    ) -> Any:
        text = _response_text(response)
        if not text:
            return response

        scores = await self._classify(text)

        if scores is None:
            team = getattr(user_api_key_dict, "team_id", None)
            blockieren = fail_closed(team, self.fail_open_teams)
            self._counters["failed_closed" if blockieren else "failed_open"] += 1
            self._write_health()
            if blockieren:
                logger.error(
                    "Moderations-Klassifikator ohne Urteil — Antwort für Team %r "
                    "BLOCKIERT (fail-closed).", team,
                )
                raise ValueError(
                    "Die Jugendschutz-Prüfung ist gerade nicht verfügbar. Bitte versuche "
                    "es in ein paar Minuten noch einmal."
                )
            logger.warning(
                "Moderations-Klassifikator ohne Urteil — Antwort für Team %r "
                "durchgelassen (fail-open).", team,
            )
            return response

        hits = violated_categories(scores, DEFAULT_CATEGORIES, self.thresholds)
        if not hits:
            self._write_health()
            return response

        self._counters["blocked"] += 1
        self._write_health()
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
