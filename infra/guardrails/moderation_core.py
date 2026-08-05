"""Entscheidungslogik des LLM-Klassifikator-Guardrails — bewusst ohne litellm-Import.

Dadurch ist sie in der backend-venv testbar (litellm lebt nur in der Proxy-venv). Die
LiteLLM-Anbindung liegt in `llm_moderation.py`; hier steht alles, was man verstehen und
prüfen können muss:

* wie der Klassifikator gefragt wird (`build_messages`),
* wie seine Antwort gelesen wird (`parse_scores`) — tolerant, weil LLMs gern Prosa oder
  ```json-Zäune um ihre Antwort legen,
* was daraus folgt (`violated_categories`).

**Ersetzt `openai_moderation`** (ADR-015 §6): Die Moderation-API gibt es bei EU-Anbietern
nicht. Betroffen sind drei Guardrails — `explicit_sexual_content`, `graphic_violence` und
`self_harm_instructions`.

⚠️ **Der heikelste Fall ist `self_harm_instructions`.** Der Guardrail darf die *fürsorgliche*
Krisenantwort NICHT blockieren — die nennt Selbstverletzung, verweist aber auf Hilfe. Genau
das ist die Antwort, die ADR-008 Teil 3 will. Ein Guardrail, der sie wegfiltert, richtet mehr
Schaden an als der Inhalt, den er verhindern soll. Die Kategoriebeschreibung unten grenzt
deshalb ausdrücklich ab, und `test_moderation_core.py` hält das fest.
"""

import json
import re

# Kategorie → (Beschreibung für den Klassifikator, Default-Schwelle)
# Die Schwellen entsprechen der bisherigen openai_moderation-Konfiguration.
DEFAULT_CATEGORIES: dict[str, tuple[str, float]] = {
    "sexual": (
        "Explizit sexuelle Darstellung. Sexualkunde, Aufklärung, Biologie und "
        "Literaturbesprechung sind KEIN Treffer.",
        0.5,
    ),
    "violence_graphic": (
        "Drastisch ausgemalte Gewaltdarstellung. Historische, journalistische oder "
        "literarische Schilderung von Gewalt im Bildungskontext ist KEIN Treffer.",
        0.7,
    ),
    "self_harm_instructions": (
        "Konkrete Anleitung, Methode, Dosierung oder Ermutigung zu Selbstverletzung oder "
        "Suizid. ACHTUNG — KEIN Treffer ist eine fürsorgliche Antwort, die Selbstverletzung "
        "oder Suizid benennt, ernst nimmt und auf Hilfsangebote verweist. Solche Antworten "
        "sind ausdrücklich erwünscht und dürfen niemals blockiert werden.",
        0.5,
    ),
}

_SYSTEM_PROMPT = (
    "Du bist ein Klassifikator für den Jugendschutz an einer Schule. Du bewertest einen "
    "Text und gibst für jede Kategorie einen Wert zwischen 0.0 (trifft nicht zu) und 1.0 "
    "(trifft eindeutig zu) aus.\n\n"
    "Antworte AUSSCHLIESSLICH mit einem JSON-Objekt, das genau die genannten Kategorien als "
    "Schlüssel enthält. Keine Erklärung, kein Fließtext.\n\n"
    "Der Text stammt aus einem schulischen Lernkontext. Bewerte zurückhaltend: Fachliche, "
    "historische und aufklärende Darstellung ist erwünscht und kein Verstoß."
)


def build_messages(text: str, categories: dict[str, tuple[str, float]] | None = None,
                   max_chars: int = 8000) -> list[dict]:
    """Baut den Klassifikator-Aufruf.

    Sehr lange Antworten werden gekürzt — für die Einschätzung genügt der Anfang, und ein
    unbegrenzter Text würde den Moderationsaufruf teurer machen als die Antwort selbst.
    """
    categories = categories or DEFAULT_CATEGORIES
    listing = "\n".join(f"- {name}: {desc}" for name, (desc, _) in categories.items())
    return [
        {"role": "system", "content": _SYSTEM_PROMPT + "\n\nKategorien:\n" + listing},
        {"role": "user", "content": text[:max_chars]},
    ]


def parse_scores(raw: str, categories: dict[str, tuple[str, float]] | None = None) -> dict[str, float] | None:
    """Liest die Klassifikator-Antwort. Gibt None zurück, wenn sie unbrauchbar ist.

    Tolerant gegenüber ```json-Zäunen und Text drumherum — aber NICHT gegenüber fehlenden
    Werten: Wer eine Kategorie nicht bewertet, hat sie nicht geprüft, und ein stillschweigend
    angenommenes 0.0 wäre eine falsche Entwarnung.
    """
    categories = categories or DEFAULT_CATEGORIES
    if not raw:
        return None
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    scores: dict[str, float] = {}
    for name in categories:
        value = data.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        scores[name] = float(value)
    return scores


def violated_categories(
    scores: dict[str, float],
    categories: dict[str, tuple[str, float]] | None = None,
    thresholds: dict[str, float] | None = None,
) -> list[str]:
    """Kategorien, deren Schwelle erreicht ist. Leer = durchlassen."""
    categories = categories or DEFAULT_CATEGORIES
    overrides = thresholds or {}
    hits = []
    for name, (_, default_threshold) in categories.items():
        threshold = overrides.get(name, default_threshold)
        if scores.get(name, 0.0) >= threshold:
            hits.append(name)
    return hits
