"""Konfiguration für die Krisen-Erkennung (ADR-008 Teil 3 + 4).

Lädt zwei versionierte YAML-Dateien:

- ``crisis_triggers.yaml`` — Keyword-/Phrasen-Trigger je Kategorie
- ``help_resources.yaml`` — interne/externe Anlaufstellen je ``help_topic``

Loader-Muster wie ``app.budget.tiers`` (Modul-Cache + ``invalidate_*``). Die Pfade
kommen aus ``settings`` (Env-Overrides ``CRISIS_TRIGGERS_PATH`` /
``HELP_RESOURCES_PATH``) und werden relativ zum Repo-Root aufgelöst, damit der
Ladevorgang unabhängig vom Arbeitsverzeichnis funktioniert (vgl.
``app.planning.calendar``).

Der eigentliche Abgleich gegen die kompilierten Patterns folgt in
``app.crisis.detector`` (Schritt 2).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, PrivateAttr, model_validator

from app.config import settings

logger = logging.getLogger(__name__)

# Repo-Root: backend/app/crisis/config.py → parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]


def normalize(text: str) -> str:
    """NFKC-Normalisierung + casefold — für case- und unicode-insensitiven Abgleich.

    Wird sowohl beim Vorkompilieren der Patterns als auch (Schritt 2) auf jede
    eingehende Nachricht angewendet, damit beide Seiten identisch normalisiert sind.
    """
    return unicodedata.normalize("NFKC", text).casefold()


def _resolve(path_str: str) -> Path:
    """Absoluter Pfad bleibt unverändert; relativer wird am Repo-Root verankert."""
    p = Path(path_str)
    return p if p.is_absolute() else _REPO_ROOT / p


# ---------------------------------------------------------------------------
# Pydantic-Modelle
# ---------------------------------------------------------------------------

Severity = Literal["info", "warning", "alert"]


class CrisisTrigger(BaseModel):
    """Ein Trigger: mehrere Regex-Patterns, die dieselbe Kategorie auslösen."""

    category: str
    severity: Severity
    patterns: list[str] = Field(min_length=1)
    help_topic: str
    coreviewer_role: str = "review"

    # Vorkompilierte Patterns (normalisiert, IGNORECASE) — kein YAML-Feld.
    _compiled: list[re.Pattern] = PrivateAttr(default_factory=list)

    @model_validator(mode="after")
    def _compile_patterns(self) -> "CrisisTrigger":
        self._compiled = [re.compile(normalize(p), re.IGNORECASE) for p in self.patterns]
        return self

    @property
    def compiled(self) -> list[re.Pattern]:
        """Die vorkompilierten Regex-Patterns (gegen normalisierten Text anwenden)."""
        return self._compiled


class CrisisTriggers(BaseModel):
    triggers: list[CrisisTrigger]


class HelpContact(BaseModel):
    """Eine Anlaufstelle (intern oder extern); außer ``name`` alles optional."""

    name: str
    contact: str | None = None
    hours: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    free_of_charge: bool | None = None
    anonymous: bool | None = None


class HelpTopic(BaseModel):
    label: str
    internal: list[HelpContact] = []
    external: list[HelpContact] = []


class HelpResources(BaseModel):
    topics: dict[str, HelpTopic]


# ---------------------------------------------------------------------------
# Loader (Modul-Cache + Invalidierung)
# ---------------------------------------------------------------------------

_triggers_cache: CrisisTriggers | None = None
_resources_cache: HelpResources | None = None


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        logger.error("Krisen-Konfiguration nicht gefunden unter %s", path)
        raise FileNotFoundError(f"Konfigurationsdatei nicht gefunden: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_crisis_triggers() -> CrisisTriggers:
    """Lädt + validiert crisis_triggers.yaml (einmalig, danach aus dem Cache)."""
    global _triggers_cache
    if _triggers_cache is not None:
        return _triggers_cache
    path = _resolve(settings.crisis_triggers_path)
    _triggers_cache = CrisisTriggers.model_validate(_load_yaml(path))
    logger.info(
        "Krisen-Trigger geladen von %s (%d Kategorien)", path, len(_triggers_cache.triggers)
    )
    return _triggers_cache


def load_help_resources() -> HelpResources:
    """Lädt + validiert help_resources.yaml (einmalig, danach aus dem Cache)."""
    global _resources_cache
    if _resources_cache is not None:
        return _resources_cache
    path = _resolve(settings.help_resources_path)
    _resources_cache = HelpResources.model_validate(_load_yaml(path))
    logger.info(
        "Hilfe-Ressourcen geladen von %s (%d Topics)", path, len(_resources_cache.topics)
    )
    return _resources_cache


def invalidate_crisis_cache() -> None:
    """Setzt beide Caches zurück (nach YAML-Änderung / Hot-Reload)."""
    global _triggers_cache, _resources_cache
    _triggers_cache = None
    _resources_cache = None


def missing_help_topics() -> list[str]:
    """``help_topic``-Werte aus den Triggern, die in help_resources.yaml fehlen.

    Leere Liste = alle Referenzen lösen auf. Dient der Validierung (Test + optional
    beim Start), damit kein Trigger auf ein nicht existierendes Topic zeigt.
    """
    known = set(load_help_resources().topics)
    return sorted(
        {t.help_topic for t in load_crisis_triggers().triggers if t.help_topic not in known}
    )
