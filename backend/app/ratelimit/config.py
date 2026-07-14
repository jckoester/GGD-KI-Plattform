"""Ratelimit-Konfiguration aus `config/rate_limits.yaml` (Sicherheits-Audit #2).

Pro Bucket ein Limit (`limit` Anfragen / `window` Sekunden, je Nutzer:in), optional pro Rolle
überschrieben (höchstes Rollen-Limit gewinnt — Lehrkräfte großzügiger als Schüler:innen).
Fehlt die Datei, greifen konservative Built-in-Defaults (kein Hard-Fail). Selten geändert.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml

from app.config import settings

logger = logging.getLogger(__name__)

# Built-in-Defaults (limit, window_sekunden) — falls die YAML fehlt oder ein Bucket fehlt.
_DEFAULTS: dict[str, tuple[int, float]] = {
    "pii_scan": (30, 60.0),
    "upload": (20, 60.0),
    "chat": (60, 60.0),
}
_FALLBACK = (60, 60.0)

_cache: Optional[dict] = None


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    path = Path(settings.rate_limits_path)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            _cache = yaml.safe_load(f) or {}
        logger.info("rate_limits geladen von %s", path)
    else:
        logger.info("rate_limits.yaml nicht gefunden (%s) — Built-in-Defaults", path)
        _cache = {}
    return _cache


def invalidate_cache() -> None:
    global _cache
    _cache = None


def resolve(bucket: str, roles: list[str]) -> tuple[int, float]:
    """Gibt (limit, window_sekunden) für Bucket + Rollen zurück."""
    cfg = _load()
    roles = roles or []

    role_cfg = cfg.get("roles") or {}
    best: Optional[tuple[int, float]] = None
    for role in roles:
        entry = (role_cfg.get(role) or {}).get(bucket)
        if entry:
            cand = (int(entry["limit"]), float(entry["window"]))
            if best is None or cand[0] > best[0]:  # großzügigstes Rollen-Limit gewinnt
                best = cand
    if best is not None:
        return best

    b = (cfg.get("buckets") or {}).get(bucket)
    if b:
        return int(b["limit"]), float(b["window"])

    return _DEFAULTS.get(bucket, _FALLBACK)
