"""In-Memory-Ratelimit-Zähler (Sicherheits-Audit #2).

Fixed-Window pro `(bucket, sub)`: dep­endency-frei, ausreichend gegen Flooding/DoS bei
Schulgröße. **Prozess-lokal** — bei mehreren uvicorn-Workern gilt das Limit je Worker
(effektiv Limit × Worker). Für strikte, worker-übergreifende Drosselung zusätzlich
nginx `limit_req_zone` (siehe Audit #5) oder ein geteilter Store (Redis) — bewusst v1-out.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

# key -> (window_start_monotonic, count)
_store: dict[str, tuple[float, int]] = {}
_lock = threading.Lock()
_MAX_KEYS = 50_000  # Backstop gegen unbegrenztes Wachstum


def allow(
    bucket: str, sub: str, limit: int, window: float, now: Optional[float] = None
) -> tuple[bool, float]:
    """Zählt eine Anfrage. Gibt (erlaubt, retry_after_sekunden) zurück.

    `limit <= 0` deaktiviert die Drosselung (immer erlaubt).
    """
    if limit <= 0:
        return True, 0.0
    key = f"{bucket}\x00{sub}"
    t = now if now is not None else time.monotonic()
    with _lock:
        start, count = _store.get(key, (t, 0))
        if t - start >= window:
            start, count = t, 0
        if count >= limit:
            return False, max(0.0, window - (t - start))
        _store[key] = (start, count + 1)
        if len(_store) > _MAX_KEYS:
            _cleanup(t)
        return True, 0.0


def _cleanup(t: float) -> None:
    """Entfernt lange abgelaufene Fenster (best effort, unter dem Lock aufgerufen)."""
    stale = [k for k, (s, _c) in _store.items() if t - s >= 3600]
    for k in stale:
        _store.pop(k, None)


def reset() -> None:
    """Leert den Store (nur für Tests)."""
    with _lock:
        _store.clear()
