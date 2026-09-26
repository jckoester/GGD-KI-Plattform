"""Audience-/rollenabhängige System-Prompt-Komposition (ADR-008 Teil 2 + 1B, D1).

Reine Funktionen (testbar, ohne DB): Auswahl der Zielgruppen-Behandlung und Aufbau des
kombinierten Pädagogik-/Assistenten-System-Inhalts. Das Laden von pedagogy.yaml liegt in
``app.pedagogy.config``; der Einbau in den Chat-Flow in ``app.chat.router``.
"""

from __future__ import annotations

from app.pedagogy.config import PedagogyConfig


def is_student_treatment(audience: str | None, user_is_student: bool) -> bool:
    """Schüler-Behandlung (student_extension + Augmentierungen) — ja/nein? (D1)

    - ``student`` → immer Schüler-Behandlung (ADR-konform)
    - ``teacher`` → immer Lehrkraft-Behandlung
    - ``all`` oder ``None`` (kein Assistent) → nach der **Rolle der anfragenden Person**
    """
    if audience == "student":
        return True
    if audience == "teacher":
        return False
    return user_is_student


def _augmentation_texts(pedagogy: PedagogyConfig, disabled: list[str] | None) -> list[str]:
    disabled_set = set(disabled or [])
    return [a.text for a in pedagogy.student_augmentations if a.key not in disabled_set]


#: Was neben der Klassenstufe steht. Ohne diesen Satz ist die Stufe eine Angabe ohne
#: Auftrag — das Modell weiß, in welcher Klasse jemand ist, und antwortet trotzdem auf
#: Kursstufenniveau.
#:
#: ⚠️ **Ausblenden wäre die schlechtere Lösung** (N6): Fragt eine Neuntklässlerin
#: ausdrücklich nach der Elektronen-Fassung der Oxidation, fände der Assistent nichts
#: und antwortete aus dem Modellwissen. Deshalb bekommt er alles zu sehen — und die
#: Regel, wonach er sich richtet.
STUFEN_REGEL = (
    "Antworte auf dem Stand dieser Klassenstufe. Spätere Inhalte nur, wenn "
    "ausdrücklich danach gefragt wird, und dann mit dem Hinweis, dass sie später "
    "genauer kommen."
)


def stufen_hinweis(stufe: int | None) -> str:
    """Die eine Zeile zur Klassenstufe — leer, wenn sie unbekannt ist."""
    if stufe is None:
        return ""
    return f"Die fragende Person ist in Klasse {stufe}. {STUFEN_REGEL}"


def compose_system_content(
    pedagogy: PedagogyConfig,
    *,
    student_treatment: bool,
    context_str: str | None,
    assistant_system_prompt: str | None,
    disabled_augmentations: list[str] | None = None,
    stufe: int | None = None,
) -> str:
    """Kombinierter Pädagogik-/Assistenten-System-Inhalt.

    Reihenfolge: universelle Basis · Zielgruppen-Erweiterung · [Klassenstufe — nur
    Schüler-Behandlung] · [Wissens-Kontext + Assistenten-Prompt] ·
    [Lernverhalten-Augmentierungen — nur Schüler-Behandlung].
    ``output_format`` hängt der Aufrufer separat als letzte System-Message an.

    ``stufe`` steht **vor** dem Kontext, nicht darin: Sie gilt für die ganze Antwort,
    auch wenn die Suche nichts gefunden hat.
    """
    extension = (
        pedagogy.preambles.student_extension
        if student_treatment
        else pedagogy.preambles.teacher_extension
    )
    parts: list[str] = [pedagogy.preambles.universal_base.strip(), extension.strip()]

    # ⚠️ **Nur bei Schüler-Behandlung.** Eine Lehrkraft, die den Unterricht einer
    # neunten Klasse vorbereitet, braucht alle Fassungen ohne Zurückhaltung — sie
    # entscheidet selbst, was in die Stunde gehört (N5).
    if student_treatment:
        hinweis = stufen_hinweis(stufe)
        if hinweis:
            parts.append(hinweis)

    ctx = (context_str or "").strip()
    prompt = (assistant_system_prompt or "").strip()
    if ctx and prompt:
        parts.append(ctx + "\n\n---\n\n" + prompt)
    elif ctx:
        parts.append(ctx)
    elif prompt:
        parts.append(prompt)

    if student_treatment:
        augs = _augmentation_texts(pedagogy, disabled_augmentations)
        if augs:
            parts.append("\n".join(augs))

    return "\n\n".join(p for p in parts if p)
