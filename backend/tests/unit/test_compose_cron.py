"""Wächter: Die Cron-Datei aus der Compose findet `python` (0.39.1).

cron startet Jobs mit `PATH=/usr/bin:/bin`; das Python des Images (`python:*-slim`) liegt unter
`/usr/local/bin`. Ohne eigene PATH-Zeile scheiterte jeder Lauf mit `python: not found` — auf Prod
von Mai bis November 2026 unbemerkt, weil die Ausgabe nur im Container-Log stand.

Der Test führt den Startbefehl des Cron-Dienstes aus, mit umgelenkten Pfaden, und prüft die
entstandene Datei — nicht den Quelltext, denn zwischen YAML und Shell liegen zwei Auslegungen.
"""
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

COMPOSE = Path(__file__).resolve().parents[3] / "docker-compose.yml"


def _cron_datei(tmp_path: Path) -> list[str]:
    befehl = yaml.safe_load(COMPOSE.read_text())["services"]["cron"]["command"]
    skript = shlex.split(befehl)[2]            # sh -c "<skript>"
    ziel = tmp_path / "ggd-ki"
    skript = (skript.replace("printenv >> /etc/environment", "true")
                    .replace("/etc/cron.d/ggd-ki", str(ziel))
                    .replace("cron -f", "true"))
    subprocess.run(["sh", "-c", skript], check=True)
    return [z for z in ziel.read_text().splitlines() if z.strip()]


@pytest.mark.skipif(shutil.which("sh") is None, reason="keine Shell")
def test_cron_datei_setzt_path_vor_den_jobs(tmp_path):
    zeilen = _cron_datei(tmp_path)
    assert zeilen[0].startswith("PATH="), "PATH muss vor dem ersten Job stehen"
    assert "/usr/local/bin" in zeilen[0].split("=", 1)[1].split(":")


@pytest.mark.skipif(shutil.which("sh") is None, reason="keine Shell")
def test_alle_jobs_stehen_in_der_datei(tmp_path):
    """Kein Job geht beim Zusammenbau verloren (z. B. durch ein `>` statt `>>`)."""
    jobs = [z for z in _cron_datei(tmp_path) if not z.startswith("PATH=")]
    erwartet = shlex.split(
        yaml.safe_load(COMPOSE.read_text())["services"]["cron"]["command"]
    )[2].count("/app/scripts/")
    assert len(jobs) == erwartet
    assert all(" root python /app/scripts/" in z for z in jobs)
