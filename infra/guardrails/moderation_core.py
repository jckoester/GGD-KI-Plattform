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

**Und den `regex`-Guardrail für Drogen-Anleitungen** (`drug_instructions`): Den Typ `regex`
gibt es seit LiteLLM 1.83.7 nicht mehr, der Proxy startet damit nicht einmal. Sein
Nachfolger `litellm_content_filter` wäre kein Drop-in — und vor allem hätte er dasselbe
Problem, vor dem `guardrails/README.md` bei Selbstverletzung warnt: Ein Muster wie
`(anleitung|rezept).{0,40}synthese` trifft den Chemieunterricht mit. Der Klassifikator
unterscheidet dagegen die Ammoniaksynthese von der Methamphetaminsynthese.

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
    "drug_instructions": (
        "Konkrete Anleitung zur Herstellung, Synthese oder Beschaffung illegaler Drogen — "
        "Reaktionswege, Mengenangaben, Bezugsquellen. ACHTUNG — KEIN Treffer sind: "
        "Chemieunterricht (auch Synthesen, Destillation, Gärung, Lösungsmittel), "
        "Suchtprävention und Aufklärung über Wirkung und Gefahren, Pharmakologie und "
        "Medikamente, sowie historische oder gesellschaftliche Betrachtung von Drogen. "
        "Entscheidend ist, ob der Text jemanden in die Lage versetzt, eine illegale Droge "
        "herzustellen oder zu beschaffen — nicht, ob Drogen vorkommen.",
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


# ── Verhalten bei Ausfall des Klassifikators ─────────────────────────────────

# Teams, die bei einem Ausfall weiterarbeiten dürfen. Alles andere wird blockiert.
DEFAULT_FAIL_OPEN_TEAMS: frozenset[str] = frozenset({"lehrkraefte"})


def fail_closed(team_id: str | None, fail_open_teams: set[str] | None = None) -> bool:
    """Soll bei ausgefallenem Klassifikator blockiert werden?

    Fail-open war die Reaktion auf eine berechtigte Sorge: Ein Guardrail, der bei
    Anbieterstoerung alles blockiert, legt den Unterricht der ganzen Schule lahm. Aber das
    Risiko ist nicht gleich verteilt — es geht um Jugendschutz. Deshalb faellt die
    Entscheidung nach Publikum:

    * **Lehrkraefte** arbeiten weiter. Eine ungeprueft durchgelassene Antwort ist hier
      vertretbar; der Ausfall der Plattform waere es nicht.
    * **Schueler:innen** werden blockiert. Eine abgewiesene Antwort ist aergerlich, eine
      ungefilterte ist genau das, was der Guardrail verhindern soll.

    Unbekanntes Team → blockieren. Wer nicht nachweislich zum ausgenommenen Kreis gehoert,
    faellt in die schuetzende Variante; ein kaputter Team-Bezug darf nicht dazu fuehren,
    dass alle als Lehrkraft behandelt werden.
    """
    erlaubt = DEFAULT_FAIL_OPEN_TEAMS if fail_open_teams is None else fail_open_teams
    return (team_id or "") not in erlaubt


# ── Betriebszustand (fuer Health-Endpunkt und Admin-Ansicht) ─────────────────

def build_health_snapshot(counters: dict[str, int], *, classifier: str | None,
                          fallback: str | None, zeitstempel: str) -> dict:
    """Baut den Zustandsbericht, den der Proxy als JSON ablegt.

    Warum ueberhaupt Zaehler: Fail-open ist nur zu verantworten, wenn man **weiss**, wie
    oft es eintritt. Eine Warnung im Proxy-Log liest niemand. Die Zahlen hier sind das,
    was ein Monitoring abfragen und woran es eine Benachrichtigung haengen kann.

    `retry_ok` ist bewusst getrennt von `primary_ok`: Haeufige, aber erfolgreiche
    Wiederholungen deuten auf etwas anderes hin (Latenz, Ueberlast, zu knappes Timeout) als
    vollstaendige Ausfaelle — und wuerden in einer gemeinsamen Erfolgsquote untergehen.
    """
    gesamt = sum(counters.get(k, 0) for k in
                 ("primary_ok", "retry_ok", "fallback_ok", "failed_open", "failed_closed"))
    fehlgeschlagen = counters.get("failed_open", 0) + counters.get("failed_closed", 0)
    return {
        "classifier_model": classifier,
        "fallback_model": fallback,
        "checked_at": zeitstempel,
        "total": gesamt,
        "counters": {k: counters.get(k, 0) for k in (
            "primary_ok", "retry_ok", "fallback_ok",
            "failed_open", "failed_closed", "blocked")},
        "failure_rate": round(fehlgeschlagen / gesamt, 4) if gesamt else 0.0,
        "healthy": fehlgeschlagen == 0,
    }
