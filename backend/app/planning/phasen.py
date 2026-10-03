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


def uebernimm_zusatzfelder(
    neu: Any, gespeichert: Any
) -> list[dict[str, Any]]:
    """Die neue Phasenliste eines Editors — mit den Feldern, die er nicht kennt (0.13, P2).

    Drei Wege schreiben Felder in eine Phase, die `LessonPhaseItem` nicht kennt: die
    Nachbereitung (`status`), das Streichen und Kürzen (`status`, `kuerzung`) und das
    Übertragen (`status`, `uebertrag_von`). Ein Editor — der Planer, das Obsidian-Plugin,
    der Planungsassistent — schickt nur die Schemafelder. Bis 0.12 verwarf jedes Speichern
    deshalb Nachbereitungsstatus, Kürzungs- und Übertragsmarke: Eine als „offen"
    nachbereitete Phase tauchte im Reflow nicht mehr auf.

    Die Regel (Entscheidung Jan, 03.10.2026):

    - Aus der **neuen** Phase zählen nur die Schemafelder. Was der Editor darüber hinaus
      schickt, bestimmt er nicht — diese Felder gehören der Nachbereitung und den
      Operationen.
    - Kommt die Phase mit einer `id`, die gespeichert ist, werden **alle** Felder der
      gespeicherten Phase übernommen, die nicht zum Schema gehören. „Alle" statt einer
      festen Liste: Das nächste Feld, das eine Operation setzt, ist gleich mit geschützt.
    - Neue Phasen (ohne oder mit unbekannter `id`) bekommen nichts — auch kein ``null``,
      denn jeder Leser behandelt ``null`` wie Fehlen, und ``"status": null`` wäre eine
      Falle (`reflow_service`: ``p.get("status", "geplant")``).
    - Was der Editor weglässt, ist weg, samt seiner Felder. Gewollt.

    Die Kennungsvergabe (`sichere_phasen_kennungen`) läuft **danach**: Eine neu vergebene
    Kennung kann nichts Gespeichertes treffen.
    """
    from app.planning.schemas import LessonPhaseItem

    schema = set(LessonPhaseItem.model_fields)
    vorher = {
        p["id"]: p
        for p in (gespeichert or [])
        if isinstance(p, dict) and isinstance(p.get("id"), str) and p["id"].strip()
    }
    ergebnis: list[dict[str, Any]] = []
    for phase in neu or []:
        if not isinstance(phase, dict):
            ergebnis.append(phase)
            continue
        eigene = {k: v for k, v in phase.items() if k in schema}
        alt = vorher.get(phase.get("id")) if isinstance(phase.get("id"), str) else None
        zusatz = {k: v for k, v in (alt or {}).items() if k not in schema}
        ergebnis.append({**eigene, **zusatz})
    return ergebnis
