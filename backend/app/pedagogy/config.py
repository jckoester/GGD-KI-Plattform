"""Laden + Validieren der pedagogy.yaml (ADR-008 Teil 1B + 2).

Loader-Muster wie ``app.crisis.config`` (Modul-Cache + ``invalidate_*``). Der Pfad
kommt aus ``settings.pedagogy_path`` (Env-Override ``PEDAGOGY_PATH``) und wird relativ
zum Repo-Root aufgelöst. Anders als crisis_triggers.yaml ist pedagogy.yaml
**versioniert** — Änderungen wirken erst nach Backend-Neustart (kein Hot-Reload).

Die eigentliche audience-/rollenabhängige Prompt-Komposition folgt in
``app.pedagogy.compose`` (Schritt 3).
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

# Repo-Root: backend/app/pedagogy/config.py → parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _resolve(path_str: str) -> Path:
    """Absoluter Pfad bleibt unverändert; relativer wird am Repo-Root verankert."""
    p = Path(path_str)
    return p if p.is_absolute() else _REPO_ROOT / p


# ---------------------------------------------------------------------------
# Pydantic-Modelle
# ---------------------------------------------------------------------------


class Augmentation(BaseModel):
    """Eine Lernverhalten-Augmentierung (nur Schüler-Behandlung, abschaltbar)."""

    key: str
    label: str
    text: str


class Preambles(BaseModel):
    universal_base: str
    student_extension: str
    teacher_extension: str


class PedagogyConfig(BaseModel):
    preambles: Preambles
    student_augmentations: list[Augmentation] = []
    output_format: str = ""


# ---------------------------------------------------------------------------
# Loader (Modul-Cache + Invalidierung)
# ---------------------------------------------------------------------------

_cache: PedagogyConfig | None = None


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        logger.error("Pädagogik-Konfiguration nicht gefunden unter %s", path)
        raise FileNotFoundError(f"Konfigurationsdatei nicht gefunden: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_pedagogy() -> PedagogyConfig:
    """Lädt + validiert pedagogy.yaml (einmalig, danach aus dem Cache)."""
    global _cache
    if _cache is not None:
        return _cache
    path = _resolve(settings.pedagogy_path)
    _cache = PedagogyConfig.model_validate(_load_yaml(path))
    logger.info(
        "Pädagogische Leitplanken geladen von %s (%d Augmentierungen)",
        path,
        len(_cache.student_augmentations),
    )
    return _cache


def invalidate_pedagogy_cache() -> None:
    """Setzt den Cache zurück (nach YAML-Änderung)."""
    global _cache
    _cache = None


def get_student_augmentations(disabled: list[str] | None = None) -> list[str]:
    """Augmentierungs-Texte für die Schüler-Behandlung, ohne die deaktivierten Keys."""
    disabled_set = set(disabled or [])
    return [
        a.text
        for a in load_pedagogy().student_augmentations
        if a.key not in disabled_set
    ]


def list_augmentations() -> list[dict]:
    """Verfügbare Augmentierungen als ``[{key, label}]`` — für die Editor-UI (Schritt 4)."""
    return [
        {"key": a.key, "label": a.label}
        for a in load_pedagogy().student_augmentations
    ]
