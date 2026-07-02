"""Moderation von Bild-Prompts (Phase 16, Schritt 3).

Der Bild-Prompt wird beim Tool-Call **vom LLM** gebildet und umgeht damit das
Frontend-PII-Gate. Diese serverseitige Prüfung läuft daher **vor** dem Aufruf des
LiteLLM-Bild-Endpoints — zusätzlich zu einer optionalen LiteLLM-`pre_call`-Guardrail
am Proxy und der provider-seitigen Moderation.

Zwei Schichten:
  1. **Krisen-Scan** (``app.crisis.detector.scan``) — für Bilder BLOCKIEREND
     (anders als im Text-Chat, ADR-008 Teil 3): zu Selbstverletzung/Suizid/Gewalt
     wird kein Bild erzeugt. Das Hilfe-Banner löst weiterhin der Scan der
     ursprünglichen Nutzernachricht im Chat-Router aus.
  2. **Kuratierte Bild-Blockliste** (``config/image_blocklist.yaml``) — jugendschutz-
     relevante Muster (sexuelle Inhalte, drastische Gewalt, Waffenbau …).

Loader-Muster wie ``app.crisis.config`` (Modul-Cache + ``invalidate_*``). Normalisierung
(NFKC + casefold) wird aus ``app.crisis.config`` wiederverwendet, damit Patterns und
Eingabe identisch normalisiert sind.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, PrivateAttr, model_validator

from app.config import settings
from app.crisis.config import normalize
from app.crisis.detector import scan as crisis_scan

logger = logging.getLogger(__name__)

# Repo-Root: backend/app/chat/image_moderation.py → parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _resolve(path_str: str) -> Path:
    """Absoluter Pfad bleibt; relativer wird am Repo-Root verankert (cwd-unabhängig)."""
    p = Path(path_str)
    return p if p.is_absolute() else _REPO_ROOT / p


class ImageBlockRule(BaseModel):
    """Eine Blockliste-Regel: mehrere Regex-Patterns mit gemeinsamer Ablehnungsbegründung."""

    category: str
    patterns: list[str] = Field(min_length=1)
    reason: str  # dem LLM/Nutzer gezeigte Begründung der Ablehnung

    _compiled: list[re.Pattern] = PrivateAttr(default_factory=list)

    @model_validator(mode="after")
    def _compile_patterns(self) -> "ImageBlockRule":
        self._compiled = [re.compile(normalize(p), re.IGNORECASE) for p in self.patterns]
        return self

    @property
    def compiled(self) -> list[re.Pattern]:
        return self._compiled


class ImageBlocklist(BaseModel):
    rules: list[ImageBlockRule] = []


_blocklist_cache: ImageBlocklist | None = None


def load_image_blocklist() -> ImageBlocklist:
    """Lädt + validiert image_blocklist.yaml (einmalig, danach aus dem Cache).

    Fehlt die Datei, wird — wie bei ``crisis_triggers.yaml`` — ein ``FileNotFoundError``
    geworfen: Die Live-Config wird beim Setup aus ``image_blocklist.example.yaml``
    provisioniert; eine fehlende Jugendschutz-Blockliste soll nicht stillschweigend
    zu schwächerer Moderation führen (fail-closed).
    """
    global _blocklist_cache
    if _blocklist_cache is not None:
        return _blocklist_cache
    path = _resolve(settings.image_blocklist_path)
    if not path.exists():
        logger.error("Bild-Blockliste nicht gefunden unter %s", path)
        raise FileNotFoundError(f"Konfigurationsdatei nicht gefunden: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    _blocklist_cache = ImageBlocklist.model_validate(data)
    logger.info("Bild-Blockliste geladen von %s (%d Regeln)", path, len(_blocklist_cache.rules))
    return _blocklist_cache


def invalidate_image_blocklist_cache() -> None:
    """Setzt den Cache zurück (nach YAML-Änderung / Hot-Reload / im Test)."""
    global _blocklist_cache
    _blocklist_cache = None


def image_prompt_block_reason(prompt: str) -> str | None:
    """Prüft einen Bild-Prompt; gibt einen Ablehnungsgrund zurück oder None (= erlaubt).

    Der Grund ist für den LLM gedacht, der daraus die Absage an die Nutzer:in
    formuliert. Er benennt bewusst nicht die konkrete Regel.
    """
    if not prompt or not prompt.strip():
        return None

    # 1) Krisen-Trigger → für Bilder blockierend.
    if crisis_scan(prompt) is not None:
        return "Zu dieser Anfrage wird kein Bild erstellt."

    # 2) Kuratierte Bild-Blockliste.
    normalized = normalize(prompt)
    for rule in load_image_blocklist().rules:
        if any(pattern.search(normalized) for pattern in rule.compiled):
            return rule.reason

    return None
