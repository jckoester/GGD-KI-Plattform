"""Bildarten — Laden + Validieren der ``image_models.yaml`` (Mehrmodell-Plan, Schritt 1).

Eine **Bildart** ist der Nutzerbegriff für „welches Bildmodell mit welchen Formaten": das,
was die Schule konfiguriert, was ein Assistent anbietet und was das LLM im Werkzeug wählt.
Das Modell dahinter ist damit austauschbar, ohne dass sich für Nutzer:innen etwas ändert —
dieselbe Eigenschaft, die die Formatnamen (``quadratisch`` statt ``1024x1024``) für Größen
schon haben, eine Ebene höher.

Abgrenzung: Gleiche Funktion, anderes Modell → Bildart. Andere Funktion → andere Fähigkeit.
Eine Mindmap ist deshalb **keine** Bildart (sie ist Code, kein Bild, und änderbar).

Warum hier und nicht in ``model_info`` der LiteLLM-Config: Deutsche Nutzertexte gehören
nicht in eine Infrastruktur-Konfiguration, die Zuständigkeiten sind verschieden — und vor
allem würde das Werkzeug-Schema sonst an einem Proxy-Roundtrip **pro Chat-Anfrage** hängen.
Hier wird es netzfrei gebaut.

Loader-Muster wie ``app.pedagogy.config`` (Modul-Cache + ``invalidate_*``). Der Pfad kommt
aus ``settings.image_models_path`` (Env-Override ``IMAGE_MODELS_PATH``) und wird am
Repo-Root verankert, damit das Laden nicht vom Arbeitsverzeichnis abhängt.

**Fail-closed bei kaputter Datei, nachsichtig bei fehlender.** Ein Tippfehler in der YAML
bricht den Start mit einer Meldung, die die gültigen Werte nennt: Ein still falsches
Bildmodell kostet Geld und umgeht Freigaben. Fehlt die Datei dagegen ganz, wird aus den
abgelösten Umgebungsvariablen (``IMAGE_DEFAULT_MODEL`` & Co.) genau **eine** Bildart
``standard`` synthetisiert — ein Update ändert damit nichts, bis jemand die Datei anlegt.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError, field_validator, model_validator

from app.config import settings

logger = logging.getLogger(__name__)

# Repo-Root: backend/app/chat/image_models.py → parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]

# Bildart-IDs landen im `enum` des Werkzeug-Schemas und in einer DB-Liste am Assistenten.
# Deshalb eng gefasst: kleingeschrieben, keine Leerzeichen, keine Sonderzeichen.
_ID_MUSTER = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_GROESSE_MUSTER = re.compile(r"^([1-9][0-9]*)x([1-9][0-9]*)$")

# `url` ist bewusst NICHT erlaubt: `LiteLLMClient.generate_image` verarbeitet nur Base64,
# damit keine extern gehosteten Bild-URLs entstehen (Datenschutzgrenze). Ein Eintrag `url`
# in der Konfiguration würde jeden Aufruf dieser Bildart in einen RuntimeError laufen
# lassen — besser beim Start abweisen als im Gespräch scheitern.
_ERLAUBTE_RESPONSE_FORMATE = {"", "b64_json"}


def _resolve(path_str: str) -> Path:
    """Absoluter Pfad bleibt unverändert; relativer wird am Repo-Root verankert."""
    p = Path(path_str)
    return p if p.is_absolute() else _REPO_ROOT / p


# ---------------------------------------------------------------------------
# Pydantic-Modelle
# ---------------------------------------------------------------------------


class Bildart(BaseModel):
    """Eine Bildart: Modell + die Formate, die es beherrscht."""

    id: str
    label: str
    beschreibung: str = ""
    modell: str                     # `model_name` aus der LiteLLM-Config (Aliasname)
    formate: dict[str, str]         # Formatname → Pixelgröße, z. B. quer → 1344x768
    standardformat: str
    # Leer = Parameter weglassen (nötig für Modelle, die ihn ablehnen und ohnehin Base64
    # liefern — gpt-image-1, FLUX.1-schnell). `b64_json` erzwingt Base64 bei Modellen, die
    # sonst eine URL lieferten.
    response_format: str = ""

    @field_validator("id")
    @classmethod
    def _id_pruefen(cls, v: str) -> str:
        if not _ID_MUSTER.match(v):
            raise ValueError(
                f"Bildart-ID '{v}' ist unzulässig. Erlaubt sind Kleinbuchstaben, Ziffern, "
                "'-' und '_'; das erste Zeichen muss ein Buchstabe oder eine Ziffer sein."
            )
        return v

    @field_validator("label", "modell")
    @classmethod
    def _nicht_leer(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Wert darf nicht leer sein.")
        return v.strip()

    @field_validator("response_format")
    @classmethod
    def _response_format_pruefen(cls, v: str) -> str:
        if v not in _ERLAUBTE_RESPONSE_FORMATE:
            raise ValueError(
                f"response_format '{v}' ist unzulässig. Gültig: '' (Parameter weglassen) "
                "oder 'b64_json'. 'url' ist ausgeschlossen — es werden ausschließlich "
                "Base64-Bilder verarbeitet, damit keine extern gehosteten Bild-URLs "
                "entstehen."
            )
        return v

    @field_validator("formate")
    @classmethod
    def _formate_pruefen(cls, v: dict[str, str]) -> dict[str, str]:
        if not v:
            raise ValueError(
                'Mindestens ein Format angeben, z. B. {"quadratisch": "1024x1024"}.'
            )
        for name, groesse in v.items():
            if not name.strip():
                raise ValueError("Formatname darf nicht leer sein.")
            if not _GROESSE_MUSTER.match(str(groesse)):
                raise ValueError(
                    f"Format '{name}': '{groesse}' ist keine Pixelgröße. Erwartet wird "
                    "BREITExHÖHE mit positiven Zahlen, z. B. '1344x768'."
                )
        return v

    @model_validator(mode="after")
    def _standardformat_pruefen(self) -> "Bildart":
        if self.standardformat not in self.formate:
            raise ValueError(
                f"Bildart '{self.id}': standardformat '{self.standardformat}' ist kein "
                f"Schlüssel aus formate. Gültig: {', '.join(sorted(self.formate))}."
            )
        return self

    def pixel(self, formatname: str) -> tuple[int, int]:
        """Breite/Höhe eines konfigurierten Formats. Validierung garantiert das Muster."""
        treffer = _GROESSE_MUSTER.match(self.formate[formatname])
        assert treffer is not None  # durch _formate_pruefen sichergestellt
        return int(treffer.group(1)), int(treffer.group(2))


class ImageModelsConfig(BaseModel):
    bildarten: list[Bildart]
    standard_bildart: str

    @model_validator(mode="after")
    def _konsistenz_pruefen(self) -> "ImageModelsConfig":
        if not self.bildarten:
            raise ValueError("Mindestens eine Bildart konfigurieren.")

        ids = [b.id for b in self.bildarten]
        doppelte = sorted({i for i in ids if ids.count(i) > 1})
        if doppelte:
            raise ValueError(
                f"Doppelte Bildart-IDs: {', '.join(doppelte)}. Jede ID darf nur einmal "
                "vorkommen — sonst entscheidet die Reihenfolge in der Datei darüber, "
                "welches Modell tatsächlich gerufen wird."
            )

        if self.standard_bildart not in ids:
            raise ValueError(
                f"standard_bildart '{self.standard_bildart}' ist keine konfigurierte "
                f"Bildart. Gültig: {', '.join(sorted(ids))}."
            )
        return self

    def get(self, bildart_id: str | None) -> Bildart | None:
        for b in self.bildarten:
            if b.id == bildart_id:
                return b
        return None

    @property
    def standard(self) -> Bildart:
        treffer = self.get(self.standard_bildart)
        assert treffer is not None  # durch _konsistenz_pruefen sichergestellt
        return treffer


# ---------------------------------------------------------------------------
# Loader (Modul-Cache + Invalidierung)
# ---------------------------------------------------------------------------

_cache: ImageModelsConfig | None = None


def _synthetisieren() -> ImageModelsConfig:
    """Eine Bildart ``standard`` aus den abgelösten Umgebungsvariablen.

    Aufwärtspfad für Installationen von vor der Einführung dieser Datei: Ohne
    ``image_models.yaml`` verhält sich die Bildgenerierung exakt wie zuvor. Die
    Variablen ``IMAGE_DEFAULT_MODEL`` / ``IMAGE_SIZES`` / ``IMAGE_DEFAULT_FORMAT`` /
    ``IMAGE_RESPONSE_FORMAT`` gelten damit als abgelöst und entfallen später.
    """
    return ImageModelsConfig(
        bildarten=[
            Bildart(
                id="standard",
                label="Standard",
                beschreibung="Aus den Umgebungsvariablen übernommen.",
                modell=settings.image_default_model,
                formate=dict(settings.image_sizes),
                standardformat=settings.image_default_format,
                response_format=settings.image_response_format,
            )
        ],
        standard_bildart="standard",
    )


def load_image_models() -> ImageModelsConfig:
    """Lädt + validiert ``image_models.yaml`` (einmalig, danach aus dem Cache)."""
    global _cache
    if _cache is not None:
        return _cache

    path = _resolve(settings.image_models_path)
    if not path.exists():
        _cache = _synthetisieren()
        logger.info(
            "Keine Bildarten-Konfiguration unter %s — eine Bildart 'standard' aus "
            "IMAGE_DEFAULT_MODEL=%r synthetisiert (Verhalten unverändert). Für mehrere "
            "Bildmodelle die Datei aus config/image_models.example.yaml anlegen.",
            path, settings.image_default_model,
        )
        return _cache

    with open(path, "r", encoding="utf-8") as f:
        roh = yaml.safe_load(f) or {}

    try:
        _cache = ImageModelsConfig.model_validate(roh)
    except ValidationError as e:
        # Fail-closed mit Pfad: Eine unbrauchbare Bildarten-Datei darf nicht in einen
        # stillen Fallback laufen — sonst erzeugt die Schule Bilder mit einem anderen
        # Modell als gedacht, womöglich unbepreist.
        raise ValueError(f"Bildarten-Konfiguration {path} ist fehlerhaft:\n{e}") from e

    logger.info(
        "Bildarten geladen von %s: %s (Standard: %s)",
        path,
        ", ".join(f"{b.id}→{b.modell}" for b in _cache.bildarten),
        _cache.standard_bildart,
    )
    return _cache


def invalidate_image_models_cache() -> None:
    """Setzt den Cache zurück (nach YAML-Änderung oder in Tests)."""
    global _cache
    _cache = None


def get_bildart(bildart_id: str | None) -> Bildart | None:
    """Bildart nach ID, oder None."""
    return load_image_models().get(bildart_id)


def default_bildart() -> Bildart:
    """Die Bildart, die gilt, wenn keine oder eine unbekannte angegeben wurde."""
    return load_image_models().standard


def alle_bildarten() -> list[Bildart]:
    return list(load_image_models().bildarten)


def referenzierte_modelle() -> list[str]:
    """Alle von Bildarten referenzierten LiteLLM-Modellnamen, ohne Dubletten.

    Grundlage für die Konfigurationsprüfung (Schritt 7): Jedes davon muss im Proxy
    existieren, ``mode: image_generation`` tragen und in ``IMAGE_PRICES`` stehen —
    sonst bucht es 0,00 $ und läuft am Budget vorbei.
    """
    gesehen: list[str] = []
    for b in load_image_models().bildarten:
        if b.modell not in gesehen:
            gesehen.append(b.modell)
    return gesehen
