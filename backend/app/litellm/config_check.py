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


def _dokumentierter_bildpreis(info: dict) -> float | None:
    """Der in `model_info` **notierte** Bildpreis, oder None.

    ``input_cost_per_image`` ist der einzige Schlüssel, den LiteLLMs Bild-Kostenrechner
    kennt (neben ``input_cost_per_pixel``). Wirksam wird er dort ohnehin nicht — für Bilder
    zählt allein ``IMAGE_PRICES``. Er steht in der Config als Dokumentation und wird nur
    dagegen abgeglichen.
    """
    wert = info.get("input_cost_per_image")
    return float(wert) if isinstance(wert, (int, float)) and wert > 0 else None


def _anbieter_id(entry: dict) -> str:
    """`litellm_params.model` eines Eintrags, z. B. ``openai/black-forest-labs/FLUX.1-schnell``."""
    return str((entry or {}).get("litellm_params", {}).get("model", ""))


def _preis_aus_image_prices(entry: dict, image_prices: dict[str, Any]) -> float | None:
    """Der für dieses Bildmodell **wirksame** Preis aus ``IMAGE_PRICES``, oder None.

    Die Schlüssel dort sind Anbieter-IDs **ohne** Provider-Präfix
    (``black-forest-labs/FLUX.1-schnell``), in der Config steht aber
    ``openai/black-forest-labs/FLUX.1-schnell``. Statt eine Liste bekannter Provider zu
    pflegen, werden beide Schreibweisen probiert — die Anbieter-ID enthält selbst häufig
    einen Schrägstrich, eine Zerlegung nach dem ersten wäre also nicht eindeutig.
    """
    ziel = _anbieter_id(entry)
    if not ziel:
        return None
    for schluessel in (ziel, ziel.partition("/")[2]):
        if schluessel and schluessel in image_prices:
            wert = image_prices[schluessel]
            return float(wert) if isinstance(wert, (int, float)) else None
    return None


def check_config(
    model_infos: list[dict],
    settings: Any,
    bildarten: Iterable[Any] | None = None,
    image_prices: dict[str, Any] | None = None,
) -> list[Finding]:
    """Gleicht die Proxy-Konfiguration gegen die `.env` und die Anforderungen ab.

    `model_infos` sind die Roh-Einträge aus `GET /model/info`. Gibt eine Liste von Funden
    zurück — leer heißt: alles, was ohne Live-Aufruf prüfbar ist, stimmt.

    `bildarten` sind die konfigurierten Bildarten (aus ``config/image_models.yaml`` bzw. der
    Synthese). Ohne Angabe werden sie geladen; Tests reichen sie durch, um ohne Datei zu
    prüfen.

    `image_prices` ist der geparste Inhalt von ``IMAGE_PRICES``, oder **None = unbekannt**.
    Die Variable wird vom **Proxy** gelesen, nicht vom Backend — läuft er auf einem anderen
    Host, ist sie hier nicht sichtbar, und das ist kein Fehler, sondern eine Prüfung, die
    dort stattfinden muss.
    """
    entries = _entries_by_name(model_infos)
    findings: list[Finding] = []

    if not entries:
        return [Finding(ERROR, "Der Proxy meldet keine Modelle (`model_list` leer?).")]

    if bildarten is None:
        from app.chat.image_models import alle_bildarten  # lokal: kein Import-Zyklus
        bildarten = alle_bildarten()
    bildarten = list(bildarten)
    bildart_modelle = {b.modell for b in bildarten}

    # ── 1. Kennen wir die in der .env genannten Modelle überhaupt? ────────────────────
    # IMAGE_DEFAULT_MODEL steht hier nicht mehr: Bildmodelle kommen aus den Bildarten
    # (Prüfung 7) — ohne eigene Datei ist das genau eine Bildart aus ebendieser Variable.
    configured = [
        ("CHAT_DEFAULT_MODEL", settings.chat_default_model, True),
        ("TITLE_MODEL", settings.title_model, False),
        ("EMBEDDING_MODEL", settings.embedding_model, True),
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
    role_modes: dict[str, str] = {settings.embedding_model: "embedding"}
    for modell in bildart_modelle:
        role_modes[modell] = "image_generation"
    for name, entry in sorted(entries.items()):
        info = _info(entry)
        mode = info.get("mode") or role_modes.get(name)
        # Lokal betriebene Modelle kosten nichts — fehlende Preise sind dort kein Fund,
        # sondern der Normalfall. Erkannt am **Anbieter**, nicht am Modellnamen: Wie eine
        # Schule ihren lokalen Eintrag nennt, ist ihre Sache. (Die Plattform liefert seit
        # 08/2026 keinen lokalen Fallback mehr mit; wer einen betreibt, tut das selbst.)
        #
        # Bewusst eng gefasst: Ein OpenAI-**kompatibler** Anbieter ist nicht automatisch
        # kostenlos — IONOS und Mistral laufen genau so. Sie hier mit auszunehmen hieße,
        # ihre fehlenden Preise zu verschweigen; und das ist der Fehler, den diese
        # Prüfung überhaupt finden soll.
        if str(info.get("litellm_provider", "")) == "ollama":
            continue
        if mode == "image_generation":
            # Ob überhaupt bepreist wird, entscheidet allein IMAGE_PRICES (Prüfung 7):
            # LiteLLM löst Bildpreise über seine eingebaute Tabelle auf und liest das
            # `model_info` des Deployments dabei nicht (gemessen 28.08.2026). Hier wird
            # deshalb nur geprüft, dass beide Stellen dasselbe sagen — die Config-Vorlagen
            # verlangen das ausdrücklich, und ein Auseinanderlaufen führt dazu, dass man
            # den falschen Wert für bare Münze nimmt.
            if info.get("output_cost_per_image") is not None and not info.get(
                "input_cost_per_image"
            ):
                findings.append(Finding(
                    WARNING,
                    f"'{name}': `output_cost_per_image` kennt LiteLLMs Bild-Kostenrechner "
                    f"nicht — er liest `input_cost_per_image` (bzw. `input_cost_per_pixel`).",
                ))
            dokumentiert = _dokumentierter_bildpreis(info)
            if image_prices is not None and dokumentiert is not None:
                wirksam = _preis_aus_image_prices(entry, image_prices)
                if wirksam is not None and abs(wirksam - dokumentiert) > 1e-9:
                    findings.append(Finding(
                        WARNING,
                        f"'{name}': model_info nennt {dokumentiert} $/Bild, IMAGE_PRICES "
                        f"{wirksam} $/Bild. Gebucht wird IMAGE_PRICES — beide Stellen "
                        f"gleich halten, sonst führt die Config in die Irre.",
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
        target = _anbieter_id(entry)
        if "<" in name or "<" in target or "TODO" in target:
            findings.append(Finding(
                ERROR, f"'{name}': Platzhalter aus der Vorlage nicht ersetzt ({target!r})."
            ))

    # ── 7. Bildarten gegen die Proxy-Config ──────────────────────────────────────────
    # Die Bildarten stehen in einer eigenen Datei; sie kann von der Proxy-Config
    # abdriften, ohne dass es auffällt. Jeder Fund hier ist ein Fall, der erst im
    # Gespräch scheitern würde.
    bild_modelle_im_proxy = sorted(
        n for n, e in entries.items() if _info(e).get("mode") == "image_generation"
    )
    for b in bildarten:
        if b.modell not in entries:
            findings.append(Finding(
                ERROR,
                f"Bildart '{b.id}' verweist auf '{b.modell}', das die LiteLLM-Config nicht "
                f"kennt. Bildmodelle im Proxy: "
                f"{', '.join(bild_modelle_im_proxy) or '— keine —'}",
            ))
            continue
        eintrag = entries[b.modell]
        if _info(eintrag).get("mode") != "image_generation":
            findings.append(Finding(
                ERROR,
                f"Bildart '{b.id}': '{b.modell}' trägt kein model_info.mode = "
                f"'image_generation'. Das Modell taucht dadurch in der Bild-Freigabe-Matrix "
                f"nicht auf und lässt sich für kein Team freischalten.",
            ))
        if image_prices is None:
            continue
        if _preis_aus_image_prices(eintrag, image_prices) is None:
            findings.append(Finding(
                WARNING,
                f"Bildart '{b.id}': '{_anbieter_id(eintrag) or b.modell}' fehlt in "
                f"IMAGE_PRICES — jedes Bild dieser Bildart wird mit 0,00 $ gebucht und "
                f"läuft am EUR-Budget vorbei. Für Bilder greift **nur** IMAGE_PRICES; "
                f"ein Preis unter model_info bleibt wirkungslos.",
            ))

    if image_prices is None:
        findings.append(Finding(
            INFO,
            "IMAGE_PRICES ist hier nicht lesbar — die Bildpreise wurden nicht geprüft. "
            "Die Variable liest der LiteLLM-Proxy; läuft er auf einem anderen Host, dort "
            "nachsehen.",
        ))

    verwaist = [n for n in bild_modelle_im_proxy if n not in bildart_modelle]
    if verwaist:
        findings.append(Finding(
            INFO,
            f"Bildmodelle ohne Bildart: {', '.join(verwaist)}. Sie lassen sich freischalten, "
            f"werden aber von keinem Assistenten genutzt — Eintrag in "
            f"config/image_models.yaml fehlt.",
        ))

    return findings
