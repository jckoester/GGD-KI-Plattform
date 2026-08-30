"""Konfigurationspfade, die im Container ins Leere zeigen.

Anlass (30.08.2026, Produktivsystem): `check_litellm_config.py` meldete „Keine
Bildarten-Konfiguration unter **/config/image_models.yaml**" — mit führendem Schrägstrich,
obwohl die Datei da war.

**Der Mechanismus.** Mehrere Module verankern relative Pfade an einer selbst berechneten
Repo-Wurzel, `Path(__file__).resolve().parents[3]`. Im Entwicklungsbaum stimmt das:

    <repo>/backend/app/chat/image_models.py   → parents[3] = <repo>

Das Image kopiert aber den **Inhalt** von `backend/` nach `/app`; die Ebene `backend/`
entfällt damit:

    /app/app/chat/image_models.py             → parents[3] = /

Aus `config/image_models.yaml` wird `/config/image_models.yaml`. Nichts stürzt ab — die
Datei gilt schlicht als nicht vorhanden. Betroffen sind Jugendschutz (Bild-Blockliste),
Krisenerkennung, pädagogische Leitplanken und die Guardrail-Zustandsanzeige: lauter Dinge,
deren Ausfall sich als „ist eben nichts konfiguriert" tarnt.

Bis der Auflösungsmechanismus selbst repariert ist (Todo „Container-Pfade"), hält die
`docker-compose.yml` dagegen, indem sie diese Pfade **absolut** übergibt. Diese Datei
sorgt dafür, dass die Liste vollständig bleibt: Wer ein weiteres Modul auf `_resolve`
umstellt, ohne den Dienst zu ergänzen, fällt hier auf — nicht erst im Betrieb.
"""
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
APP = REPO / "backend" / "app"
COMPOSE = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
DIENSTE = ("backend", "cron")

# Einstellung → Ort im Container. Wächst mit `test_liste_ist_vollstaendig` mit.
ABSOLUT_NOETIG = {
    "PEDAGOGY_PATH": "/app/config/pedagogy.yaml",
    "CRISIS_TRIGGERS_PATH": "/app/config/crisis_triggers.yaml",
    "HELP_RESOURCES_PATH": "/app/config/help_resources.yaml",
    "IMAGE_MODELS_PATH": "/app/config/image_models.yaml",
    "IMAGE_BLOCKLIST_PATH": "/app/config/image_blocklist.yaml",
    "GUARDRAIL_HEALTH_FILE": "/app/data/guardrail_health.json",
}


@pytest.mark.parametrize("dienst", DIENSTE)
@pytest.mark.parametrize("variable,erwartet", sorted(ABSOLUT_NOETIG.items()))
def test_pfad_wird_absolut_uebergeben(dienst, variable, erwartet):
    """Ohne diese Übergabe sucht der Container in `/config/…` statt in `/app/config/…`."""
    gesetzt = COMPOSE["services"][dienst].get("environment", {}).get(variable)
    assert gesetzt == erwartet, (
        f"Dienst '{dienst}': {variable} fehlt oder ist falsch ({gesetzt!r}). "
        f"Der relative Vorgabewert landet im Container bei '/config/…' und die Datei "
        f"gilt als nicht vorhanden — ohne Fehlermeldung."
    )


def test_liste_ist_vollstaendig():
    """Findet Module, die neu über die berechnete Repo-Wurzel auflösen.

    Gesucht wird `_resolve(settings.<name>)` — das Muster, mit dem die betroffenen Module
    ihre Pfade verankern. Jede so aufgelöste Einstellung braucht oben einen Eintrag,
    sonst zeigt sie im Container ins Leere.
    """
    gefunden: set[str] = set()
    for datei in sorted(APP.rglob("*.py")):
        if "__pycache__" in datei.parts:
            continue
        quelle = datei.read_text(encoding="utf-8")
        # Nur Module, die die Wurzel wirklich selbst berechnen.
        if "_REPO_ROOT = Path(__file__)" not in quelle:
            continue
        gefunden.update(re.findall(r"_resolve\(settings\.(\w+)\)", quelle))

    erwartet = {name.lower() for name in ABSOLUT_NOETIG}
    fehlend = {name for name in gefunden if name not in erwartet}

    assert fehlend == set(), (
        f"Diese Einstellungen werden an der berechneten Repo-Wurzel verankert, aber in "
        f"der docker-compose.yml nicht absolut übergeben: {sorted(fehlend)}. "
        f"Entweder dort ergänzen — oder besser die Auflösung reparieren."
    )


def test_wurzelberechnung_stimmt_im_entwicklungsbaum():
    """Hält fest, warum es hier funktioniert und dort nicht — die Ebene `backend/`.

    Fällt dieser Test, hat sich das Verzeichnislayout geändert; dann ist nicht dieser
    Test anzupassen, sondern die Auflösung in den Modulen.
    """
    modul = APP / "chat" / "image_models.py"
    assert modul.resolve().parents[3] == REPO

    # Dieselbe Rechnung auf dem Container-Pfad, den das Image erzeugt:
    im_container = Path("/app/app/chat/image_models.py")
    assert im_container.parents[3] == Path("/"), (
        "Genau das ist der Fehler: Im Container fehlt die Ebene `backend/`."
    )
