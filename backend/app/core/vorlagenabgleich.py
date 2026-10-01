"""Was die mitgelieferte Vorlage kennt und die eigene Konfiguration nicht.

**Das Problem, zweimal erlebt.** Die Instanzdateien unter ``config/`` werden bei der
Installation einmal aus der ``.example`` kopiert und danach **nie** überschrieben — das
ist richtig so, es sind Entscheidungen der Schule. Die Kehrseite: Was eine neue Fassung
hinzufügt, erreicht bestehende Installationen nicht und meldet sich auch nicht. Nach dem
Release 0.11 blieb so die Startseite unsichtbar, weil ``welcome`` nur in
``ui_levels.example.yaml`` stand (Jan, 29.09.2026).

Bei Navigationseinträgen ist das ärgerlich. Bei einem **Sicherheitsauslöser** ist es
etwas anderes: Dort bedeutet ein nicht übernommener Abschnitt, dass eine Prüfung
schlicht nicht stattfindet — und niemand bemerkt es, weil der Chat ja normal antwortet.

Dieses Modul ist deshalb die allgemeine Form des Wächters, den ``app/ui/levels.py`` für
die Darstellungsstufen schon hatte: Es vergleicht eine Liste benannter Einträge gegen die
Vorlage und meldet, was fehlt. Zwei gleichartige Wächter wären die nächste Stelle, die
auseinanderläuft.

⚠️ **Die Vorlage ist Diagnosemittel, nicht Voraussetzung.** Fehlt sie oder ist sie
unlesbar, unterbleibt der Abgleich stillschweigend; die Anwendung läuft unverändert.
Ein Wächter, der den Start verhindert, wäre schlimmer als das Problem, das er meldet.

⚠️ **Es wird nichts automatisch übernommen.** Krisenmuster und Gefahrenthemen sind
Schulentscheidungen — die Meldung nennt den Namen und die Folge, den Rest tut ein Mensch.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def beispielpfad(pfad: Path) -> Path:
    """``config/x.yaml`` → ``config/x.example.yaml``.

    Nur das letzte ``.yaml`` wird ersetzt; ein Verzeichnis namens ``…yaml…`` im Pfad
    bleibt damit unberührt.
    """
    return pfad.with_suffix("").with_suffix(".example.yaml") if pfad.suffixes else pfad


def fehlende_namen(pfad: Path, *, liste: str, schluessel: str) -> list[str]:
    """Namen aus der Vorlage, die in der eigenen Datei fehlen — in Vorlagenreihenfolge.

    ``liste`` ist der Schlüssel der Liste (``triggers``, ``themen``), ``schluessel`` das
    Namensfeld darin (``category``, ``thema``).
    """
    beispiel = beispielpfad(pfad)
    if not beispiel.exists() or not pfad.exists():
        return []
    try:
        vorbild = _namen(beispiel, liste, schluessel)
        eigene = set(_namen(pfad, liste, schluessel))
    except Exception as fehler:  # defekte oder unerwartet geformte Datei
        logger.debug("Vorlagenabgleich für %s nicht möglich (%s)", pfad.name, fehler)
        return []
    return [n for n in vorbild if n not in eigene]


def _namen(pfad: Path, liste: str, schluessel: str) -> list[str]:
    with open(pfad, "r", encoding="utf-8") as f:
        daten = yaml.safe_load(f) or {}
    eintraege = daten.get(liste) or []
    return [str(e[schluessel]) for e in eintraege if isinstance(e, dict) and schluessel in e]


def melde_fehlende(
    pfad: Path, *, liste: str, schluessel: str, bezeichnung: str, folge: str,
    hinweis: str = "",
) -> list[str]:
    """Meldet je fehlendem Eintrag eine Warnung. Liefert die Namen (für Tests).

    ``bezeichnung`` benennt die Art des Eintrags („Die Krisenkategorie"), ``folge`` sagt
    in einem Satz, was ohne ihn **nicht** geschieht. Die Folge ist der eigentliche Inhalt
    der Meldung: „Eintrag fehlt" bewegt niemanden, „löst dafür nicht aus" schon.
    """
    fehlend = fehlende_namen(pfad, liste=liste, schluessel=schluessel)
    for name in fehlend:
        logger.warning(
            "KONFIGURATION: %s %r steht in %s, aber nicht in Ihrer %s. %s "
            "Nach einem Update ist das der Normalfall: Die eigene Datei wird nie "
            "überschrieben.%s",
            bezeichnung, name, beispielpfad(pfad).name, pfad.name, folge,
            f" {hinweis}" if hinweis else "",
        )
    return fehlend
