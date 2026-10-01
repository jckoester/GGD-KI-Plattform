"""Was der Proxy über ein Modell weiß — gebündelt, zwischengespeichert, einmal geholt.

**Wozu.** Bis 0.12 las das Backend aus ``GET /model/info`` genau **ein** Feld
(``supports_function_calling``), obwohl dieselbe Antwort Preise, Kontextfenster und
weitere Fähigkeiten mitliefert. Wer einen Assistenten anlegt, stand damit vor einer
Liste von Namen ohne jede Entscheidungshilfe.

⚠️ **Das Kontextfenster fehlt oft — und zwar nicht zufällig.** Gemessen am 29.09.2026 an
31 Deployments: Preise bei 29, Kontextfenster bei **17**. Es fehlen alle IONOS- und alle
lokalen Modelle, weil LiteLLM die Größe nur für Modelle seiner eingebauten Tabelle kennt.
Ausgerechnet im Referenzfall der Anbieterunabhängigkeit ist die Angabe also leer. Sie ist
deshalb **kein Pflichtfeld der Oberfläche**, sondern eins, das die Proxy-Config liefern
muss (``model_info.max_input_tokens``) — so steht es in `docs/admin/modell-szenarien.md`.
Die Oberfläche muss die Leerstelle vertragen, ohne eine Zahl zu erfinden.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from app.litellm.client import LiteLLMClient

logger = logging.getLogger(__name__)

#: Die mediane Nachricht, gemessen am 01.10.2026 über 522 Nachrichten mit Tokenzahlen.
#: Der hohe Eingabewert stammt von den seit 0.11 mitgehenden Wissensbausteinen.
#:
#: ⚠️ Sie dient **nur der Schätzung** — abgerechnet wird nach echtem Verbrauch. Dieselbe
#: Größe nutzt die Skalenprüfung in ``app/litellm/config_check.py``: Eine zweite
#: Referenz hieße zwei Zahlen, die auseinanderlaufen.
REFERENZ_NACHRICHT = (2941, 530)

#: Deployments ändern sich nur mit der Proxy-Config.
TTL_SEKUNDEN = 60.0


@dataclass(frozen=True)
class Eigenschaften:
    """Was über ein Modell bekannt ist. ``None`` heißt **unbekannt**, nicht „nein"."""

    funktionsaufrufe: bool | None = None
    denkt: bool | None = None
    bilder: bool | None = None
    kontextfenster: int | None = None
    preis_ein_usd: float | None = None
    preis_aus_usd: float | None = None

    @property
    def usd_je_nachricht(self) -> float | None:
        """Was eine **mediane** Nachricht kostet — Schätzung für den Modellwähler.

        ``None``, wenn kein Eingabepreis bekannt ist: Eine Null wäre an dieser Stelle
        eine Falschauskunft („kostenlos"), und genau solche Preislücken meldet
        ``check_litellm_config.py`` als Fehler.
        """
        if not self.preis_ein_usd:
            return None
        ein, aus = REFERENZ_NACHRICHT
        return ein * self.preis_ein_usd + aus * (self.preis_aus_usd or 0.0)


_cache: tuple[float, dict[str, Eigenschaften]] | None = None


def invalidate_eigenschaften_cache() -> None:
    """Verwirft den Cache. Für Tests und nach Änderungen an der Proxy-Config."""
    global _cache
    _cache = None


def _aus_eintrag(eintrag: dict) -> Eigenschaften:
    info = eintrag.get("model_info") or {}
    return Eigenschaften(
        funktionsaufrufe=info.get("supports_function_calling"),
        denkt=info.get("supports_reasoning"),
        bilder=info.get("supports_vision"),
        kontextfenster=info.get("max_input_tokens"),
        preis_ein_usd=info.get("input_cost_per_token"),
        preis_aus_usd=info.get("output_cost_per_token"),
    )


async def alle_eigenschaften() -> dict[str, Eigenschaften]:
    """Modellname → Eigenschaften. Bei Störung ein leeres Dict, nie ein Fehler.

    Ein unerreichbarer Proxy darf den Modellwähler nicht leeren — er zeigt dann
    Namen ohne Zusatzangaben, so wie vor 0.12.
    """
    global _cache
    if _cache is not None and time.monotonic() - _cache[0] < TTL_SEKUNDEN:
        return _cache[1]
    client = LiteLLMClient()
    try:
        eintraege = await client.get_model_deployments()
    except Exception:
        logger.warning("Modell-Eigenschaften nicht abrufbar", exc_info=True)
        return {}
    finally:
        await client.close()

    # Erster Treffer gewinnt: Zeigt ein Alias auf mehrere Deployments, ist die Angabe
    # ohnehin mehrdeutig — eine gemittelte Zahl wäre eine erfundene Genauigkeit.
    gebaut: dict[str, Eigenschaften] = {}
    for e in eintraege:
        name = e.get("model_name")
        if name and name not in gebaut:
            gebaut[name] = _aus_eintrag(e)
    _cache = (time.monotonic(), gebaut)
    return gebaut
