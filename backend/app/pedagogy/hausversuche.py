"""Sicherheitsauslöser für Versuche zu Hause (Paket 9, N12).

**Warum es diese Schicht gibt.** Punkt 8 der Schüler-Präambel verbietet gefährliche
Versuchsvorschläge. Gemessen am 26.09.2026 hält er nicht: Auf „Kann ich Wasser zu Hause
mit einer Batterie zerlegen?" empfahl der Assistent einen Elektrolyse-Aufbau mit Natron-
oder Kalilauge — die Regel stand wörtlich im selben Prompt. Eine allgemeine Regel in
einer langen Präambel wird mit einer gewissen Wahrscheinlichkeit befolgt, und für
Laugen in Kinderhand ist diese Wahrscheinlichkeit zu niedrig.

Diese Schicht macht aus der allgemeinen Regel eine **konkrete Anweisung für genau diese
Antwort** — kurz, benannt und an der letzten Stelle des Systemtexts, also dort, wo sie
am schwersten zu überlesen ist.

⚠️ **Es ist keine Sperre.** Der Chat läuft weiter, die Frage wird beantwortet, nur ohne
Anleitung. Wer eine harte Grenze braucht, ist auf der Guardrail-Ebene des Proxys
richtig. Dass eine Prompt-Anweisung wiederum nur wahrscheinlich befolgt wird, gilt auch
hier — sie ist nur erheblich schwerer zu übersehen als ein Punkt unter acht.

**Die beiden Listen sind mit UND verknüpft** — im Regelfall. Eine Absicht („mache ich
selbst, zu Hause") **und** ein riskantes Thema. Ohne diese Kopplung verweigerte der
Assistent auch die Erklärung einer Elektrolyse im Unterricht, und das ist
Chemieunterricht, kein Sicherheitsproblem.

**Die Ausnahme: Themen ohne Absicht** (``absicht_noetig: false``). Manche Fragen sind
heikel, ohne dass jemand etwas vorhat — „Wie viel Koffein ist tödlich?" nennt keine
Absicht und ist trotzdem keine Frage, auf die eine Menge für Menschen gehört. Solche
Themen tragen deshalb eine **eigene Anweisung** (``anweisung:``): Die Versuchsanweisung
(„keine Materialliste, keinen Aufbau") passt auf sie nicht, sie ist auf Anleitungen
gemünzt. Ein Thema ohne Absicht und ohne eigenen Text wäre ein Widerspruch, der
niemandem auffällt — fehlt der Text, bleibt es bei der Versuchsanweisung.

⚠️ **Ein Thema ohne Absicht greift breiter als die anderen.** Es sieht nur noch das
Thema, nicht mehr den Vorsatz — die Muster müssen deshalb enger sein. „tödlich" allein
trifft „Warum ist Kohlenstoffmonooxid tödlich?", also Unterricht.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, PrivateAttr, model_validator

from app.config import settings
from app.core.paths import aufloesen
from app.crisis.config import normalize

logger = logging.getLogger(__name__)


class Gefahrenthema(BaseModel):
    """Ein riskantes Thema samt dem Satz, der dem Modell erklärt, warum."""

    thema: str
    hinweis: str
    patterns: list[str] = Field(min_length=1)
    #: Greift das Thema auch **ohne** Absichtsbekundung? Vorgabe: nein — die UND-Kopplung
    #: ist der Regelfall und hält den Unterricht frei.
    absicht_noetig: bool = True
    #: Eigener Anweisungstext statt der Versuchsanweisung. Platzhalter ``{hinweis}``.
    anweisung: str | None = None

    _compiled: list[re.Pattern] = PrivateAttr(default_factory=list)

    @model_validator(mode="after")
    def _kompiliere(self) -> "Gefahrenthema":
        self._compiled = [re.compile(normalize(p)) for p in self.patterns]
        return self

    @property
    def compiled(self) -> list[re.Pattern]:
        return self._compiled


class Hausversuche(BaseModel):
    absicht: list[str] = Field(min_length=1)
    themen: list[Gefahrenthema] = Field(min_length=1)

    _absicht_compiled: list[re.Pattern] = PrivateAttr(default_factory=list)

    @model_validator(mode="after")
    def _kompiliere(self) -> "Hausversuche":
        self._absicht_compiled = [re.compile(normalize(p)) for p in self.absicht]
        return self

    @property
    def absicht_compiled(self) -> list[re.Pattern]:
        return self._absicht_compiled


_cache: Hausversuche | None = None


def load_hausversuche() -> Hausversuche:
    """Lädt + validiert die Auslöserliste (einmalig, danach aus dem Cache)."""
    global _cache
    if _cache is not None:
        return _cache
    pfad: Path = aufloesen(settings.home_experiment_triggers_path)
    if not pfad.exists():
        logger.error("Hausversuchs-Auslöser nicht gefunden unter %s", pfad)
        raise FileNotFoundError(f"Konfigurationsdatei nicht gefunden: {pfad}")
    with open(pfad, "r", encoding="utf-8") as f:
        _cache = Hausversuche.model_validate(yaml.safe_load(f) or {})
    logger.info(
        "Hausversuchs-Auslöser geladen von %s (%d Themen)", pfad, len(_cache.themen)
    )
    return _cache


def invalidate_hausversuche_cache() -> None:
    global _cache
    _cache = None


def pruefe(text: str) -> Gefahrenthema | None:
    """Fragt die Nachricht nach einem gefährlichen Versuch für zu Hause?

    Liefert das erste passende Thema in YAML-Reihenfolge oder ``None``. **Keine
    Rangfolge nach Schwere** wie bei den Krisen-Triggern: Die Anweisung lautet in jedem
    Fall „nicht anleiten"; welches der zutreffenden Themen genannt wird, ändert nur den
    Begründungssatz. Eine Rangfolge wäre eine Zusage, die niemand einlösen kann — ist
    Lauge gefährlicher als Netzstrom?
    """
    if not text or not text.strip():
        return None
    normalisiert = normalize(text)
    konfig = load_hausversuche()

    # Erst die Themen, die für sich allein stehen. Sie zuerst zu prüfen ist nicht nur
    # Reihenfolge, sondern Bedingung: Stünden sie in der Schleife unten, käme der
    # Absichts-Check davor und ihre Zusage („auch ohne Absicht") wäre keine.
    for thema in konfig.themen:
        if thema.absicht_noetig:
            continue
        if any(p.search(normalisiert) for p in thema.compiled):
            return thema

    if not any(p.search(normalisiert) for p in konfig.absicht_compiled):
        return None
    for thema in konfig.themen:
        if thema.absicht_noetig and any(p.search(normalisiert) for p in thema.compiled):
            return thema
    return None


def gefahr_fuer(text: str, *, student_treatment: bool) -> Gefahrenthema | None:
    """Greift die Regel für **diese** Nachricht? — die Entscheidung an einer Stelle.

    ⚠️ **Nur in der Schüler-Behandlung**, und zwar aus demselben Grund, aus dem Punkt 8
    der Präambel nur dort steht: Wer eine Stunde zur Elektrolyse vorbereitet, braucht
    den Aufbau. Die Zielgruppe entscheidet sich nach ``audience`` des Assistenten, nicht
    nach der Rolle allein (D1) — deshalb kommt sie hier als Parameter an, statt hier
    noch einmal abgeleitet zu werden.
    """
    if not student_treatment:
        return None
    return pruefe(text)


def anweisung(thema: Gefahrenthema) -> str:
    """Der Satz, der für diese eine Antwort an den Systemtext gehängt wird.

    ⚠️ **Er nennt das Thema, statt allgemein zu warnen.** „Sei vorsichtig mit
    Versuchen" ist das, was in der Präambel schon steht und nicht gereicht hat. Was
    wirkt, ist die benannte Sache — und ein Grund, den die Schüler:in in der Antwort
    wiederfindet, statt nur eine Absage.

    Trägt das Thema einen eigenen Text (``anweisung:``), gilt dieser. Nötig für Themen,
    bei denen nicht angeleitet, sondern **nicht beziffert** werden soll: „keine
    Materialliste, keinen Aufbau" geht an einer Frage nach einer tödlichen Menge vorbei.
    """
    if thema.anweisung:
        # `replace` statt `str.format`: Der Text kommt aus der Konfiguration und darf
        # geschweifte Klammern enthalten, ohne dass die Anweisung mit KeyError ausfällt
        # — und eine Sicherheitsanweisung, die an einer Klammer scheitert, fällt
        # lautlos aus, weil der Chat ja weiterläuft.
        return thema.anweisung.replace("{hinweis}", thema.hinweis)
    return (
        f"Zu dieser Frage: Sie betrifft {thema.hinweis}. Leite das nicht an — keine "
        f"Materialliste, keinen Aufbau, keine Mengen, auch nicht abgeschwächt oder als "
        f"„nur zur Information“. Sag in einem Satz, worum es geht, in einem zweiten, "
        f"warum es in den Unterricht gehört, und biete an, die Sache zu erklären oder "
        f"einen ungefährlichen Versuch vorzuschlagen."
    )
