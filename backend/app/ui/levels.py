"""Darstellungsstufen — welcher Navigationseintrag ab welcher Stufe erscheint.

Die Oberfläche ist über die Phasen hinweg stark gewachsen. Wer sie täglich benutzt,
sieht den Funktionsumfang, der die Arbeit trägt; wer sich zum ersten Mal anmeldet, sieht
eine Wand. Die Stufen lassen sie schmal beginnen und von der Nutzer:in selbst erweitern.

⚠️ **Ein Anzeige-Filter, keine Berechtigung** (Leitprinzip 1 der Konzeptnotiz vom
28.07.2026). Was eine Stufe verbirgt, bleibt über Direktlink und API erreichbar. Rechte
stehen ausschließlich im Rollenmodell (ADR-003) — eine zweite, parallel wirkende
Sperrschicht mit ganz anderer Motivation würde dessen Prüfbarkeit verwässern und bei
jedem neuen Endpunkt die Frage aufwerfen, welche der beiden greift.

Deshalb liest dieses Modul die Zuordnung nur aus und liefert sie aus; es entscheidet
nichts. Die Zuordnung liegt in `config/ui_levels.yaml`, damit ein geänderter Zuschnitt
kein Release kostet — der Startvorschlag ist ausdrücklich ein Vorschlag.
"""
from __future__ import annotations

import os
import logging
from difflib import get_close_matches
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator, model_validator

from app.core.paths import aufloesen

_DEFAULT_PATH = aufloesen(
    os.environ.get("UI_LEVELS_PATH", "") or "config/ui_levels.yaml"
)


# Die Navigationseinträge, die es überhaupt gibt.
#
# **Warum hier und nicht in der YAML.** Die Datei entscheidet, auf welcher Stufe ein
# Eintrag liegt — das ändert sich mit Erfahrung und soll ohne Release änderbar sein.
# WELCHE Einträge es gibt, ändert sich dagegen nur, wenn die Oberfläche selbst sich
# ändert; das gehört zum Code. Die Trennung fängt den teuersten Fehler ab: Ein Tippfehler
# in der YAML (`libary`) ließe den Eintrag lautlos verschwinden, und niemand wüsste, warum
# die Bibliothek fehlt.
#
# Ab Schritt 3 prüft ein Wächtertest, dass die Sidebar genau diese Schlüssel verwendet.
logger = logging.getLogger(__name__)

BEKANNTE_EINTRAEGE = frozenset({
    "chat",              # Neuer Chat
    "assistants",        # Assistenten (Übersicht)
    "assistants_my",     # Meine Assistenten (Lehrkraft)
    "tools",             # Werkzeuge
    "library",           # Bibliothek
    "knowledge",         # Wissensbereich (Suche, Meine Bausteine, Graph)
    "curricula",         # Curricula
    "education_plans",   # Bildungspläne und Leitperspektiven
    "subjects",          # Meine Fächer
    "planner",           # Unterrichtsplanung (Jahresübersicht, Stundenentwurf)
    "history",           # Letzte Chats / Verlauf
})


class Stufe(BaseModel):
    stufe: int
    name: str
    beschreibung: str
    # „Braucht einmalig ein eingerichtetes Wochenraster" — eine ehrliche Angabe, was das
    # Freischalten kostet. Ohne sie schaltet jemand frei und steht vor einer leeren Seite.
    aufwand: str | None = None
    eintraege: list[str]


class RollenStufen(BaseModel):
    startstufe: int = 1
    stufen: list[Stufe]

    @field_validator("stufen")
    @classmethod
    def _aufsteigend_und_lueckenlos(cls, v: list[Stufe]) -> list[Stufe]:
        """Stufen sind 1..n ohne Lücke.

        Eine Lücke (1, 2, 4) wäre kein Tippfehler mit harmloser Folge: „Stufe 3" gäbe es
        dann nicht, und wer von 2 aufsteigt, spränge unbemerkt über einen Block Funktionen.
        """
        nummern = [s.stufe for s in v]
        if nummern != list(range(1, len(v) + 1)):
            raise ValueError(f"Stufen müssen 1..n lückenlos sein, gefunden: {nummern}")
        return v

    @model_validator(mode="after")
    def _startstufe_existiert(self):
        if not any(s.stufe == self.startstufe for s in self.stufen):
            raise ValueError(f"startstufe {self.startstufe} gibt es nicht")
        return self

    @model_validator(mode="after")
    def _eintrag_gehoert_genau_einer_stufe(self):
        """Kein Eintrag in zwei Stufen — sonst ist unbestimmt, ab wann er erscheint."""
        gesehen: dict[str, int] = {}
        for s in self.stufen:
            for e in s.eintraege:
                if e in gesehen:
                    raise ValueError(
                        f"Eintrag '{e}' steht in Stufe {gesehen[e]} und {s.stufe}"
                    )
                gesehen[e] = s.stufe
        return self

    #: Was beim Laden übergangen wurde — für die Meldung, nicht für die Anwendung.
    ignoriert: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _nur_bekannte_eintraege(self):
        """Unbekannte Einträge werden **entfernt und gemeldet**, nicht abgewiesen.

        ⚠️ **Bis zum 24.09.2026 warf das hier.** Der Grund war gut — ein Tippfehler
        (`libary`) ließe die Bibliothek lautlos verschwinden, und niemand wüsste, warum.
        Die Folge war es nicht: `load_ui_levels()` scheiterte dann **ganz**, `GET
        /ui/levels` antwortete mit 500, und ohne geladene Registry zeigt die Oberfläche
        *alles* an. Aus einem fehlenden Eintrag wurde so eine Navigation ohne jede
        Stufung.

        Praktisch aufgefallen ist es anders herum: `config/ui_levels.yaml` ist
        gitignored und überlebt jeden Zweigwechsel. Ein Schlüssel aus einem neueren
        Zweig (`welcome`) legte auf dem älteren **zehn Integrationstests** lahm — und
        `scripts/test.sh` ist der Pre-Push-Hook. Dasselbe passiert bei einem Rollback in
        der Produktion: Die Konfiguration weiß dann mehr als der Code.

        Beide Fälle sehen gleich aus und lassen sich nicht sicher trennen. Deshalb:
        weiterlaufen, den Eintrag weglassen — und **laut** sagen, was fehlt. Die Meldung
        schlägt zusätzlich einen bekannten Schlüssel vor, wenn der unbekannte ihm ähnelt;
        genau das trennt den Tippfehler von der Versionsdifferenz.

        Die **Beispieldatei** bleibt streng geprüft: `test_beispiel_kennt_alle_eintraege`
        vergleicht ihre Einträge mit `BEKANNTE_EINTRAEGE`, ein Tippfehler dort fällt also
        weiter auf.
        """
        unbekannt = sorted(
            {e for st in self.stufen for e in st.eintraege if e not in BEKANNTE_EINTRAEGE}
        )
        if unbekannt:
            for st in self.stufen:
                st.eintraege = [e for e in st.eintraege if e in BEKANNTE_EINTRAEGE]
            self.ignoriert = tuple(unbekannt)
        return self

    @property
    def hoechste(self) -> int:
        return len(self.stufen)

    def eintraege_bis(self, stufe: int) -> list[str]:
        """Alle Einträge bis einschließlich `stufe` — Stufen sind kumulativ."""
        return [e for s in self.stufen if s.stufe <= stufe for e in s.eintraege]


class UiLevels(BaseModel):
    rollen: dict[str, RollenStufen]

    def fuer(self, rollen: list[str]) -> RollenStufen | None:
        """Die Stufen der wirksamen Rolle.

        `teacher` gewinnt vor `student`: Admin ist eine Erweiterung der Lehrkraft-Rolle
        (CLAUDE.md, Rollenmodell) und bekommt deshalb keinen eigenen Zuschnitt.
        """
        for name in ("teacher", "student"):
            if name in rollen and name in self.rollen:
                return self.rollen[name]
        return None


# Schlüssel in `user_preferences.preferences`. Kein Schemawechsel nötig — das Feld ist
# JSONB, wie `hidden_subjects` und `cost_granularity` es vormachen.
STUFEN_SCHLUESSEL = "ui_level"


def stufe_fuer(prefs: dict, rollen: list[str], cfg: "UiLevels | None" = None) -> int | None:
    """Die wirksame Stufe einer Nutzer:in — oder ``None``.

    ``None`` heißt **nicht** „Stufe 0", sondern: Für diese Rolle sind keine Stufen
    hinterlegt, der Filter gilt nicht, es wird alles gezeigt. Der Rückgabetyp zwingt die
    aufrufende Stelle, diesen Fall zu behandeln — gäbe die Funktion hier `1` zurück,
    verschwände für eine unbekannte Rolle stillschweigend fast die ganze Navigation.

    **Fehlt der Schlüssel, gilt die Startstufe.** Bestandsnutzer:innen bekommen ihn
    einmalig per Migration auf die höchste Stufe gesetzt (Alembic 0064) — wer die
    Plattform heute benutzt, verliert nichts. Danach heißt „nicht gesetzt" verlässlich
    „neu".

    **Gelesen wird immer geklemmt.** Ein Wert außerhalb 1..höchste — aus einer älteren
    Konfiguration mit mehr Stufen, oder von Hand gesetzt — dürfte niemals eine leere
    Navigation erzeugen. 0 oder negativ wäre genau das.
    """
    c = cfg or load_ui_levels()
    r = c.fuer(rollen)
    if r is None:
        return None
    try:
        wert = int(prefs.get(STUFEN_SCHLUESSEL, r.startstufe))
    except (TypeError, ValueError):
        return r.startstufe
    return max(1, min(r.hoechste, wert))


def _meldung_zu_ignorierten(rolle: str, unbekannt: tuple[str, ...]) -> str:
    """Eine Zeile, die sagt, was fehlt — und wahrscheinlich warum.

    ⚠️ Der Vorschlag ist der Kern: Liegt der unbekannte Schlüssel **nah** an einem
    bekannten, ist es fast sicher ein Tippfehler und der Eintrag fehlt jetzt in der
    Navigation. Liegt er weit weg, stammt er vermutlich aus einer anderen Fassung —
    nach einem Rollback oder einem Zweigwechsel. Beides sieht in der Datei gleich aus;
    erst der Abstand trennt sie.
    """
    teile = []
    for e in unbekannt:
        nah = get_close_matches(e, BEKANNTE_EINTRAEGE, n=1, cutoff=0.7)
        teile.append(f"{e!r} (meinten Sie {nah[0]!r}?)" if nah else repr(e))
    return (
        f"Rolle {rolle!r}: unbekannte Navigationseinträge übergangen — {', '.join(teile)}. "
        f"Bekannt sind: {sorted(BEKANNTE_EINTRAEGE)}. "
        "Diese Einträge erscheinen nicht in der Navigation."
    )


@lru_cache(maxsize=1)
def load_ui_levels(path: Path | None = None) -> UiLevels:
    p = path or _DEFAULT_PATH
    with open(p, encoding="utf-8") as f:
        cfg = UiLevels.model_validate(yaml.safe_load(f))
    for rolle, stufen in cfg.rollen.items():
        if stufen.ignoriert:
            logger.warning("KONFIGURATION: %s", _meldung_zu_ignorierten(rolle, stufen.ignoriert))
    return cfg
