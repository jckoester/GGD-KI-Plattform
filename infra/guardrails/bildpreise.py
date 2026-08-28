"""Trägt Bildpreise in LiteLLMs Kostentabelle ein — beim Start des Proxys.

**Warum es das braucht.** Für Chat- und Embedding-Modelle greift der Preis aus
`model_info` in der LiteLLM-Config. Für **Bilder nicht**: LiteLLMs Bild-Kostenrechner
(`default_image_cost_calculator`, Stand 1.83.7) löst Preise ausschließlich über die
eingebaute Tabelle `litellm.model_cost` auf und zieht das `model_info` des Deployments gar
nicht heran. Ein Modell, das dort nicht steht — jedes selbst eingetragene —, wird mit
**0,00 $** abgerechnet. Kein Fehler, keine Warnung: Die Bildgenerierung läuft schlicht am
EUR-Budget vorbei, und das fällt erst auf, wenn die Kostenstatistik nicht mehr stimmt.

**Warum nicht am Proxy vorbei buchen.** Die Kosten im Backend selbst zu berechnen wäre
einfacher, würde aber die Budget-Durchsetzung aushebeln: Das harte Limit (429 bei
erschöpftem Budget) zieht LiteLLM aus seinen SpendLogs. Was dort nicht ankommt, begrenzt
niemand — Schüler:innen könnten ihr Budget über Bilder beliebig überziehen. Deshalb der
Weg **durch** LiteLLM: `register_model` macht seinen eigenen Rechner zuständig, und Header,
SpendLog, Budget und Statistik stimmen ohne Sonderweg zusammen.

**Einbindung** (LiteLLM-Config):

    litellm_settings:
      callbacks: ["bildpreise.registrierung"]

Der Callback tut zur Laufzeit nichts — die Arbeit passiert beim Import. Er ist nur der
Aufhänger, über den LiteLLM das Modul überhaupt lädt.

**Preise** kommen aus der Umgebung, nicht aus dem Code — sie ändern sich beim Anbieter,
nicht bei uns:

    IMAGE_PRICES={"black-forest-labs/FLUX.1-schnell": 0.032}

Schlüssel ist die **Modell-ID beim Anbieter** ohne LiteLLM-Provider-Präfix, Wert der Preis
je Bild in USD (LiteLLM rechnet in USD; die EUR-Budgets werden über den EZB-Kurs
umgerechnet). Der Wert gilt größenunabhängig.

Kostet ein Modell je nach Format unterschiedlich (FLUX.2 rechnet nach Megapixeln), muss der
Schlüssel die Größe tragen — im Format `<breite>-x-<höhe>/<modell-id>`, also
`1024-x-1024/FLUX.2-klein-4B`. Achtung: Ein solcher Eintrag gilt **nur** für diese eine
Größe; jede weitere braucht ihren eigenen, sonst fällt sie wieder auf 0,00 $ zurück.
"""

import json
import logging
import os
from typing import Any

import litellm
from litellm.integrations.custom_logger import CustomLogger

logger = logging.getLogger("litellm.bildpreise")

_ENV = "IMAGE_PRICES"


def _gelesen() -> dict[str, float]:
    roh = os.environ.get(_ENV, "").strip()
    if not roh:
        return {}
    try:
        daten = json.loads(roh)
    except json.JSONDecodeError as exc:
        logger.error(
            "%s ist kein gültiges JSON (%s) — Bilder werden mit 0,00 $ abgerechnet.",
            _ENV, exc,
        )
        return {}
    if not isinstance(daten, dict):
        logger.error("%s muss ein Objekt sein (Modell-ID → Preis).", _ENV)
        return {}

    preise: dict[str, float] = {}
    for modell, preis in daten.items():
        try:
            preise[str(modell)] = float(preis)
        except (TypeError, ValueError):
            logger.error("%s: Preis für '%s' ist keine Zahl — Eintrag ignoriert.",
                         _ENV, modell)
    return preise


def registriere_bildpreise() -> dict[str, float]:
    """Trägt die konfigurierten Bildpreise ein. Rückgabe: was tatsächlich gesetzt wurde."""
    preise = _gelesen()
    if not preise:
        logger.warning(
            "Keine Bildpreise konfiguriert (%s). Selbst eingetragene Bildmodelle werden "
            "dann mit 0,00 $ abgerechnet und laufen am EUR-Budget vorbei.", _ENV,
        )
        return {}

    for modell, preis in preise.items():
        litellm.register_model({
            modell: {"input_cost_per_image": preis, "mode": "image_generation"}
        })
    logger.info("Bildpreise registriert: %s",
                ", ".join(f"{m} = {p} $" for m, p in sorted(preise.items())))
    return preise


class Bildpreisregistrierung(CustomLogger):
    """Aufhänger, damit LiteLLM dieses Modul überhaupt lädt.

    Als `CustomLogger`, weil `litellm_settings.callbacks` das erwartet — die Klasse hakt
    sich bewusst in keinen Ereignispfad ein.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.registriert = registriere_bildpreise()


registrierung = Bildpreisregistrierung()
