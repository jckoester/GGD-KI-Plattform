"""Prüft, ob eine LiteLLM-Konfiguration die Anforderungen der Plattform erfüllt.

Hintergrund: Mehrere Dinge brechen **still**, wenn die Proxy-Config unvollständig ist — man
merkt es erst Wochen später an der Kostenstatistik oder an fehlenden Werkzeugen:

* **Fehlende Preise** → SpendLogs melden 0 → EUR-Budgets, 429-Enforcement, `/budget` und
  `/statistics/costs` laufen ins Leere. Betrifft jedes Modell, das LiteLLM nicht aus seiner
  eingebauten Preistabelle kennt — also alles, was als `openai/<id>` mit eigener `api_base`
  läuft (IONOS, OVH, lokale Server).
* **Fehlendes `supports_function_calling`** → der Tool-Loop hängt Werkzeuge entweder gar
  nicht an oder schickt sie an ein Modell, das sie nicht kann.
* **Fehlendes `mode`** → Bildmodelle tauchen in der Freigabe-Matrix nicht auf.
* **Modellnamen in der `.env`, die der Proxy nicht kennt** → 400er ohne erkennbare Ursache.

Die Prüflogik ist bewusst frei von I/O, damit sie ohne laufenden Proxy testbar ist;
`scripts/check_litellm_config.py` holt die Daten und ruft sie auf.
"""

from dataclasses import dataclass
from typing import Any, Iterable

ERROR = "error"
WARNING = "warning"
INFO = "info"


@dataclass(frozen=True)
class Finding:
    level: str
    message: str


def _entries_by_name(model_infos: Iterable[dict]) -> dict[str, dict]:
    """`/model/info`-Einträge nach `model_name`; bei Dubletten gewinnt der erste."""
    out: dict[str, dict] = {}
    for entry in model_infos:
        name = (entry or {}).get("model_name")
        if name and name not in out:
            out[name] = entry
    return out


def _info(entry: dict) -> dict:
    return (entry or {}).get("model_info") or {}


def _has_price(info: dict, *keys: str) -> bool:
    """Mindestens einer der Preis-Schlüssel ist gesetzt und > 0."""
    return any(isinstance(info.get(k), (int, float)) and info[k] > 0 for k in keys)


def _has_any_price(info: dict) -> bool:
    """Irgendein positiver Kostenschlüssel — für Modalitäten mit uneinheitlichen Modellen.

    Bildmodelle rechnen sehr unterschiedlich ab: DALL·E pro Bild (`output_cost_per_image`),
    gpt-image-1 pro **Bild-Token** (`input_cost_per_image_token`), andere pro Pixel. Eine
    feste Schlüsselliste erzeugt hier Fehlalarme; die einzig sinnvolle Frage ist, ob LiteLLM
    überhaupt einen Preis kennt.
    """
    return any(
        "cost" in key and isinstance(value, (int, float)) and value > 0
        for key, value in info.items()
    )


def check_config(model_infos: list[dict], settings: Any) -> list[Finding]:
    """Gleicht die Proxy-Konfiguration gegen die `.env` und die Anforderungen ab.

    `model_infos` sind die Roh-Einträge aus `GET /model/info`. Gibt eine Liste von Funden
    zurück — leer heißt: alles, was ohne Live-Aufruf prüfbar ist, stimmt.
    """
    entries = _entries_by_name(model_infos)
    findings: list[Finding] = []

    if not entries:
        return [Finding(ERROR, "Der Proxy meldet keine Modelle (`model_list` leer?).")]

    # ── 1. Kennen wir die in der .env genannten Modelle überhaupt? ────────────────────
    configured = [
        ("CHAT_DEFAULT_MODEL", settings.chat_default_model, True),
        ("TITLE_MODEL", settings.title_model, False),
        ("EMBEDDING_MODEL", settings.embedding_model, True),
        ("IMAGE_DEFAULT_MODEL", settings.image_default_model, False),
    ]
    for var, name, required in configured:
        if not name:
            if required:
                findings.append(Finding(ERROR, f"{var} ist nicht gesetzt."))
            continue
        if name not in entries:
            findings.append(Finding(
                ERROR,
                f"{var}='{name}' kommt in der LiteLLM-Config nicht vor. "
                f"Verfügbar: {', '.join(sorted(entries))}",
            ))

    # ── 2. Preise — sonst Spend = 0 und die Budgets greifen nicht ─────────────────────
    # Die Modalität kommt aus `model_info.mode`; fehlt sie, leiten wir sie aus der Rolle in
    # der `.env` ab. Sonst würde ein Embedding-Modell ohne `mode` zusätzlich für einen
    # fehlenden `output_cost_per_token` gerügt — den es gar nicht gibt. Das fehlende `mode`
    # selbst meldet Prüfung 4.
    role_modes = {
        settings.embedding_model: "embedding",
        settings.image_default_model: "image_generation",
    }
    for name, entry in sorted(entries.items()):
        info = _info(entry)
        mode = info.get("mode") or role_modes.get(name)
        if name == "ollama-fallback" or str(info.get("litellm_provider", "")) == "ollama":
            continue  # lokal, kostenlos
        if mode == "image_generation":
            if not _has_any_price(info):
                findings.append(Finding(
                    WARNING,
                    f"'{name}': kein Bildpreis hinterlegt — erzeugte Bilder werden mit 0 "
                    f"abgerechnet. Je nach Modell ist das `output_cost_per_image` (pro Bild) "
                    f"oder `input_cost_per_image_token` (pro Bild-Token).",
                ))
            continue
        if mode == "embedding":
            if not _has_price(info, "input_cost_per_token"):
                findings.append(Finding(
                    WARNING,
                    f"'{name}': kein input_cost_per_token — Embedding-Kosten "
                    f"erscheinen als 0.",
                ))
            continue
        if not _has_price(info, "input_cost_per_token", "input_cost_per_second"):
            findings.append(Finding(
                ERROR,
                f"'{name}': kein input_cost_per_token. Der Spend bleibt 0, damit greifen "
                f"Budget-Tiers und das 429-Enforcement nicht. "
                f"Umrechnung: Preis pro Mio ÷ 1_000_000.",
            ))
        if not _has_price(info, "output_cost_per_token", "output_cost_per_second"):
            findings.append(Finding(
                ERROR, f"'{name}': kein output_cost_per_token (siehe oben)."
            ))

    # ── 3. Tool-Fähigkeit des Standard-Chatmodells ───────────────────────────────────
    chat_name = settings.chat_default_model
    if chat_name in entries:
        fc = _info(entries[chat_name]).get("supports_function_calling")
        if fc is None:
            findings.append(Finding(
                ERROR,
                f"'{chat_name}': supports_function_calling ist nicht gesetzt. Das Backend "
                f"kann die Tool-Fähigkeit dann nicht bestimmen — Wissensgraph-, Planungs- "
                f"und Bild-Werkzeuge verhalten sich unvorhersehbar.",
            ))
        elif fc is False:
            findings.append(Finding(
                WARNING,
                f"'{chat_name}' kann kein Function-Calling. Assistenten mit Werkzeugen "
                f"brauchen ein anderes Modell.",
            ))

    # ── 4. Modalitäten korrekt markiert ──────────────────────────────────────────────
    image_name = settings.image_default_model
    if image_name and image_name in entries:
        if _info(entries[image_name]).get("mode") != "image_generation":
            findings.append(Finding(
                ERROR,
                f"'{image_name}': model_info.mode ist nicht 'image_generation'. Das Modell "
                f"taucht dadurch in der Bild-Freigabe-Matrix nicht auf.",
            ))
    embed_name = settings.embedding_model
    if embed_name and embed_name in entries:
        if _info(entries[embed_name]).get("mode") != "embedding":
            findings.append(Finding(
                WARNING,
                f"'{embed_name}': model_info.mode ist nicht 'embedding'. Funktioniert, "
                f"erschwert aber die Trennung der Modalitäten.",
            ))

    # ── 5. Sichtbarkeit im Modellwähler ──────────────────────────────────────────────
    hidden_prefixes = tuple(settings.model_picker_hidden_prefixes)
    hidden = sorted(n for n in entries if hidden_prefixes and n.startswith(hidden_prefixes))
    pickable = sorted(n for n in entries if n not in hidden)
    findings.append(Finding(
        INFO, f"Im Modellwähler sichtbar: {', '.join(pickable) or '— keine —'}"
    ))
    if hidden:
        findings.append(Finding(INFO, f"Ausgeblendet: {', '.join(hidden)}"))

    if settings.title_model and settings.title_model in pickable:
        findings.append(Finding(
            WARNING,
            f"TITLE_MODEL='{settings.title_model}' erscheint im Modellwähler. Es ist nicht "
            f"zur manuellen Auswahl gedacht — mit einem Präfix aus "
            f"MODEL_PICKER_HIDDEN_PREFIXES benennen (z. B. 'system-titel'). "
            f"Achtung: freigeschaltet bleiben muss es trotzdem.",
        ))

    # ── 6. Platzhalter aus der Vorlage übrig? ────────────────────────────────────────
    for name, entry in sorted(entries.items()):
        target = str((entry or {}).get("litellm_params", {}).get("model", ""))
        if "<" in name or "<" in target or "TODO" in target:
            findings.append(Finding(
                ERROR, f"'{name}': Platzhalter aus der Vorlage nicht ersetzt ({target!r})."
            ))

    return findings
