"""Kann die Anwendung dort schreiben, wo sie zur Laufzeit schreibt? (0.15.1)

Zwei Funktionen der Oberfläche schreiben in `config/`: die Budget-Stufen (`/budget` →
`budget_tiers.yaml`) und der Ferienkalender (`/settings/holidays` → `school_year.yaml`).
Bis 0.15.0 hängte die mitgelieferte `docker-compose.yml` das Verzeichnis schreibgeschützt
ein (`./config:/app/config:ro`). Beide Funktionen scheiterten damit auf Produktion — und
zwar erst beim Speichern, mit einem 500.

Geprüft wird das **Verzeichnis**, nicht die Datei: Beide schreiben eine temporäre Datei
daneben und ersetzen dann (`replace`). Eine schreibbare Datei in einem schreibgeschützten
Verzeichnis nützt also nichts.

Geprüft wird durch **Anlegen und Löschen einer Probedatei** — dasselbe, was nachher
geschieht. `os.access` beantwortet nur eine verwandte Frage: für die reale statt die
wirksame Nutzerkennung, und auf Netzlaufwerken mit Rechteabbildung mitunter falsch.

Dieselbe Prüfung gilt beim Start für die Ablagen unter `data/` (Bilder, Bibliothek,
Export-Vorlagen). Sie legen ihr Verzeichnis beim ersten Schreiben selbst an; fehlt es noch,
wird der nächste vorhandene Vorfahr geprüft — dort entstünde es.

**Weich, nicht hart** — wie Mail und Systemkonto: Ein schreibgeschütztes `config/` ist ein
zulässiger Betrieb für alle, die die Dateien von Hand pflegen, und Chat, Planung und
Verwaltung hängen nicht daran. Die beiden Seiten sagen es dann selbst und sperren
„Speichern" (Feld `schreibschutz` in ihren Antworten).
"""
from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.core.paths import aufloesen

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Schreibziel:
    ordner: Path
    wozu: str


def grund(ordner: Path) -> str | None:
    """``None``, wenn sich in ``ordner`` schreiben lässt — sonst der Grund."""
    ziel = ordner
    while not ziel.exists():
        if ziel.parent == ziel:
            return "kein Teil des Pfads existiert"
        ziel = ziel.parent
    if not ziel.is_dir():
        return f"{ziel} ist kein Verzeichnis"
    try:
        fd, probe = tempfile.mkstemp(prefix=".schreibprobe-", dir=ziel)
        os.close(fd)
        os.unlink(probe)
    except OSError as exc:
        return exc.strerror or str(exc)
    return None


def config_ziele() -> list[Schreibziel]:
    from app.config import settings
    from app.planning.calendar import _DEFAULT_PATH

    return [
        Schreibziel(aufloesen(settings.budget_tiers_path).parent, "Budget-Stufen (/budget)"),
        Schreibziel(_DEFAULT_PATH.parent, "Ferienkalender (/settings/holidays)"),
    ]


def daten_ziele() -> list[Schreibziel]:
    from app.config import settings

    return [
        Schreibziel(aufloesen(settings.image_storage_dir), "erzeugte Bilder"),
        Schreibziel(aufloesen(settings.artifact_storage_dir), "Bibliothek"),
        Schreibziel(aufloesen(settings.export_template_dir), "Export-Vorlagen"),
    ]


def schreibschutz(datei: Path) -> str | None:
    """Meldung für die Oberfläche, wenn ``datei`` nicht geschrieben werden kann.

    ``None`` heißt: schreibbar. Der Text richtet sich an Admins und nennt die Abhilfe.
    """
    ursache = grund(datei.parent)
    if ursache is None:
        return None
    return (
        f"{datei.parent} ist nicht schreibbar ({ursache}) — Änderungen lassen sich hier "
        f"nicht speichern. Abhilfe: das Verzeichnis ohne „:ro“ einhängen bzw. dem Backend "
        f"Schreibrechte geben, dann `docker compose up -d` (siehe Admin-Doku, "
        f"„Konfigurationsdateien“)."
    )


def pruefe_beim_start() -> list[Schreibziel]:
    """Protokolliert jedes Verzeichnis, in das nicht geschrieben werden kann.

    Gibt die betroffenen Ziele zurück (für Tests). Mehrere Ziele im selben Verzeichnis
    erscheinen in **einer** Zeile.
    """
    nach_ordner: dict[Path, list[str]] = {}
    for ziel in [*config_ziele(), *daten_ziele()]:
        nach_ordner.setdefault(ziel.ordner, []).append(ziel.wozu)

    betroffen: list[Schreibziel] = []
    for ordner, wozu in nach_ordner.items():
        ursache = grund(ordner)
        if ursache is None:
            continue
        betroffen.extend(Schreibziel(ordner, w) for w in wozu)
        logger.warning(
            "Nicht schreibbar: %s (%s). Betroffen: %s. Abhilfe: Verzeichnis ohne „:ro“ "
            "einhängen bzw. dem Backend Schreibrechte geben.",
            ordner, ursache, ", ".join(wozu),
        )
    return betroffen
