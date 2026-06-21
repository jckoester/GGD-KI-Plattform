"""Krisen-Erkennung — Abgleich einer Nachricht gegen die kuratierten Trigger.

Reine, deterministische Funktion: kein DB-Zugriff, keine Seiteneffekte. Liest die
(gecachte) Konfiguration aus ``app.crisis.config`` und liefert höchstens **einen**
Treffer pro Nachricht — bei mehreren Treffern gewinnt die höchste Severity, bei
Gleichstand die Reihenfolge in ``crisis_triggers.yaml``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.crisis.config import Severity, load_crisis_triggers, normalize

# alert > warning > info
_SEVERITY_RANK: dict[str, int] = {"info": 1, "warning": 2, "alert": 3}


class CrisisHit(BaseModel):
    """Ergebnis einer positiven Erkennung — bewusst **ohne** Klartext der Nachricht."""

    model_config = ConfigDict(frozen=True)

    category: str
    severity: Severity
    help_topic: str
    trigger_rule: str  # "crisis_triggers:<category>" — referenziert die Regel, kein Text
    coreviewer_role: str


def scan(text: str) -> CrisisHit | None:
    """Prüft eine Nutzer-Nachricht gegen alle Trigger.

    Gibt den schwersten Treffer zurück (alert > warning > info; bei Gleichstand der
    erste in YAML-Reihenfolge) oder ``None``, wenn nichts greift. Der Abgleich
    erfolgt auf der normalisierten Eingabe (NFKC + casefold), passend zu den
    vorkompilierten Patterns.
    """
    if not text or not text.strip():
        return None

    normalized = normalize(text)
    best = None
    for trigger in load_crisis_triggers().triggers:
        if any(pattern.search(normalized) for pattern in trigger.compiled):
            if best is None or _SEVERITY_RANK[trigger.severity] > _SEVERITY_RANK[best.severity]:
                best = trigger

    if best is None:
        return None

    return CrisisHit(
        category=best.category,
        severity=best.severity,
        help_topic=best.help_topic,
        trigger_rule=f"crisis_triggers:{best.category}",
        coreviewer_role=best.coreviewer_role,
    )
