"""Stabile Kennungen für Stundenphasen (AP6b, Schritt 3).

`LessonPhaseItem.id` ist `Optional` — historisch, weil die Phasen anfangs nur eine
Liste waren. Inzwischen hängt daran mehr, als der Typ verrät:

- `phasen_status` schlüsselt nach `phase_id` (Nachbereitung, UP-5),
- `TransferPhases` wählt die zu übertragenden Phasen über ihre Kennung,
- die Materialkanten vermerken die Phasen, in denen ein Baustein vorkommt (AP6b).

Fehlt die Kennung, fällt nichts davon aus — es wird still ungenau. Deshalb wird
sie beim Speichern vergeben, statt sich auf die Oberfläche zu verlassen.

**Warum das nötig ist, obwohl der Editor Kennungen vergibt:** Der
Planungsassistent schreibt seine Phasen als Roh-Dicts aus den Werkzeug-Argumenten
(`assistant_tools.py`) und geht dabei nicht durch `LessonPhaseItem`. Seine Phasen
hätten sonst nie eine Kennung.
"""
from __future__ import annotations

import uuid
from typing import Any


def sichere_phasen_kennungen(phasen: Any) -> list[dict[str, Any]]:
    """Gibt die Phasenliste zurück, in der jede Phase eine `id` trägt.

    Vorhandene Kennungen bleiben unangetastet — sie sind Referenzen: `phasen_status`
    und übertragene Phasen zeigen darauf, und eine neu vergebene Kennung ließe
    diese Verweise ins Leere laufen.

    Als „vorhanden" gilt nur eine nichtleere Zeichenkette. `None` und `""` kommen
    beide vor: `patch_lesson` speichert mit `model_dump(exclude_none=False)`, eine
    Phase ohne Kennung landet also als ``"id": null`` in den Metadaten.

    Nicht-Dicts werden unverändert durchgereicht — kaputte Daten sollen hier nicht
    den Speichervorgang sprengen; darüber wacht die Schema-Validierung.
    """
    ergebnis: list[dict[str, Any]] = []
    for phase in phasen or []:
        if not isinstance(phase, dict):
            ergebnis.append(phase)
            continue
        vorhanden = phase.get("id")
        if isinstance(vorhanden, str) and vorhanden.strip():
            ergebnis.append(phase)
        else:
            ergebnis.append({**phase, "id": str(uuid.uuid4())})
    return ergebnis
