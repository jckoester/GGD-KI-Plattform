"""Kalendertage werden lokal abgeleitet, nicht aus der Weltzeit.

Anlass (11.09.2026, 01:26 Uhr): `test_heute_zaehlt_noch_nicht_als_zukunft` kippte
über Nacht, ohne dass jemand etwas geändert hatte. Der Test leitete „heute" mit
``date.today()`` ab (lokal), die geprüfte Funktion mit
``datetime.now(timezone.utc).date()``. Zwischen Mitternacht und 02:00 MESZ laufen
die beiden auseinander — in UTC war noch der Vortag.

**Die Regel dahinter ist kein Testdetail.** Ein Schuljahresende, ein Ablaufdatum, ein
Unterrichtstag sind Daten im Kalender der Schule. Die Frage „liegt das in der
Zukunft?" beantwortet nicht die Weltzeit. In dem Zwei-Stunden-Fenster hielt
``vorgeschlagenes_ablaufdatum`` den Vortag für heute: Am Tag des Schuljahresendes
hätte ein um 00:30 angelegter Baustein ein Ablaufdatum bekommen — und der nächtliche
Lauf hätte ihn sofort archiviert. Genau der Fall, den die Prüfung dort verhindern
soll.

Gemessen waren es **zwei** Stellen gegen **zwölf**, die es schon richtig machten
(``app/context/ablauf.py`` und ``app/crons/node_lifecycle_service.py`` — die beiden,
die zusammenarbeiten). Beide sind angeglichen; dieser Test hält es fest.

⚠️ **Nicht betroffen: Zeitstempel.** ``datetime.now(timezone.utc)`` für ``created_at``,
``archived_at`` oder ``flagged_at`` ist richtig und bleibt — das sind Zeitpunkte, keine
Kalendertage, und sie werden gegen andere Zeitstempel verglichen. Verboten ist allein,
daraus ein ``date`` zu machen.

**Was dieser Test nicht löst:** Die Container laufen ohne ``TZ`` und damit in UTC —
dort ist ``date.today()`` dasselbe wie das UTC-Datum, und das Fenster besteht weiter,
nur einheitlich. Das ist eine Betriebsentscheidung (``TZ=Europe/Berlin`` in der
Compose) und steht als eigener Punkt in der Todo.
"""
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
QUELLEN = sorted(
    p for ordner in ("app", "scripts")
    for p in (BACKEND / ordner).rglob("*.py")
)

# `datetime.now(timezone.utc).date()`, `datetime.utcnow().date()` und Varianten mit
# Zeilenumbruch dazwischen.
UTC_KALENDERTAG = re.compile(
    r"(?:datetime\.)?(?:now\(\s*(?:datetime\.)?timezone\.utc\s*\)|utcnow\(\))"
    r"\s*\.\s*date\(\s*\)"
)


def test_es_gibt_ueberhaupt_quelldateien():
    """Sonst prüfte der Test unten eine leere Menge und wäre immer grün."""
    assert len(QUELLEN) > 100


def test_kein_modul_leitet_einen_kalendertag_aus_utc_ab():
    treffer = []
    for pfad in QUELLEN:
        text = pfad.read_text(encoding="utf-8")
        for zeile_nr, zeile in enumerate(text.splitlines(), start=1):
            # Kommentare zählen nicht — dieselbe Falle wie beim Picker-Wächter:
            # Die Erklärung, warum die Schreibweise falsch ist, enthält sie selbst.
            ohne_kommentar = zeile.split("#", 1)[0]
            if UTC_KALENDERTAG.search(ohne_kommentar):
                treffer.append(f"{pfad.relative_to(BACKEND)}:{zeile_nr}")

    assert not treffer, (
        "Kalendertage lokal ableiten (`date.today()`), nicht aus UTC. Betroffen: "
        f"{treffer}. Ein Schultag ist ein Datum im Kalender der Schule; zwischen "
        "Mitternacht und 02:00 MESZ liefert UTC den Vortag. Für echte Zeitstempel "
        "(`created_at`, `archived_at`) bleibt `datetime.now(timezone.utc)` richtig — "
        "nur `.date()` darauf ist es nicht."
    )


@pytest.mark.parametrize(
    "schreibweise",
    [
        "heute = datetime.now(timezone.utc).date()",
        "x = datetime.utcnow().date()",
        "stichtag = now(timezone.utc).date()",
        "y = datetime.now( timezone.utc ).date()",
    ],
)
def test_der_wachhund_erkennt_die_schreibweisen(schreibweise):
    """Gegenprobe im Test selbst: Ein Muster, das nichts trifft, wäre stumm grün."""
    assert UTC_KALENDERTAG.search(schreibweise)


@pytest.mark.parametrize(
    "erlaubt",
    [
        "archived_at=datetime.now(timezone.utc)",
        "jetzt = datetime.now(timezone.utc)",
        "heute = date.today()",
        "stichtag = heute or date.today()",
    ],
)
def test_der_wachhund_schlaegt_bei_zeitstempeln_nicht_an(erlaubt):
    assert not UTC_KALENDERTAG.search(erlaubt)
