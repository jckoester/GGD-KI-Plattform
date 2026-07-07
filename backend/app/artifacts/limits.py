"""Aufbewahrung + Quota der Artefaktbibliothek — role-/jahrgangsbasiert (Phase 18).

Lädt `config/artifact_limits.yaml` (Struktur wie `budget_tiers.yaml`: `grades:` + `roles:`).
Fehlt die Datei, greifen konservative Built-in-Defaults — **kein Hard-Fail** (Limits sind
operativ, nicht sicherheitskritisch). Selten geändert; kein UI.
"""
import logging
from pathlib import Path
from typing import Optional

import yaml

from app.config import settings

logger = logging.getLogger(__name__)

# Built-in-Defaults (falls die YAML fehlt oder ein Wert nicht konfiguriert ist).
_DEFAULT_TEACHER = {"retention_days": 730, "quota_bytes": 1073741824}    # 2 Jahre / 1 GB
_DEFAULT_STUDENT = {"retention_days": 365, "quota_bytes": 52428800}      # 1 Jahr / 50 MB
_DEFAULT_FALLBACK = _DEFAULT_STUDENT

_cache: Optional[dict] = None


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    path = Path(settings.artifact_limits_path)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            _cache = yaml.safe_load(f) or {}
        logger.info("artifact_limits geladen von %s", path)
    else:
        logger.warning("artifact_limits.yaml nicht gefunden (%s) — Built-in-Defaults", path)
        _cache = {}
    return _cache


def invalidate_cache() -> None:
    global _cache
    _cache = None


def get_artifact_limits(roles: list[str], grade: Optional[int]) -> tuple[int, int]:
    """Gibt (retention_days, quota_bytes) für die Nutzer:in zurück.

    teacher (auch teacher+admin) → `roles.teacher`; student → `grades[grade]`; sonst Fallback.
    """
    cfg = _load()
    roles = roles or []

    if "teacher" in roles:
        t = (cfg.get("roles") or {}).get("teacher") or _DEFAULT_TEACHER
        return int(t["retention_days"]), int(t["quota_bytes"])

    if "student" in roles and grade is not None:
        grades = cfg.get("grades") or {}
        g = grades.get(grade) or grades.get(str(grade)) or _DEFAULT_STUDENT
        return int(g["retention_days"]), int(g["quota_bytes"])

    return _DEFAULT_FALLBACK["retention_days"], _DEFAULT_FALLBACK["quota_bytes"]
