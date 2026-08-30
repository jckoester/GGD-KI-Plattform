"""Konfigurationspfade in beiden Verzeichnislayouts.

Anlass (30.08.2026, Produktivsystem): `check_litellm_config.py` meldete „Keine
Bildarten-Konfiguration unter **/config/image_models.yaml**" — mit führendem Schrägstrich,
obwohl die Datei da war.

**Der Mechanismus.** Acht Module verankerten relative Pfade an einer selbst berechneten
Wurzel, `Path(__file__).resolve().parents[3]` (in einem Fall `[4]`). Im Entwicklungsbaum
stimmte das:

    <repo>/backend/app/chat/image_models.py   → parents[3] = <repo>

Das Image kopiert aber den **Inhalt** von `backend/` nach `/app`; die Ebene `backend/`
entfällt damit:

    /app/app/chat/image_models.py             → parents[3] = /

Aus `config/image_models.yaml` wurde `/config/image_models.yaml`. Nichts stürzte ab — die
Datei galt schlicht als nicht vorhanden. Betroffen waren Jugendschutz (Bild-Blockliste),
Krisenerkennung, pädagogische Leitplanken und die Guardrail-Zustandsanzeige: lauter Dinge,
deren Ausfall sich als „ist eben nichts konfiguriert" tarnt.

Seit dem Umbau löst `app/core/paths.aufloesen` zentral auf. Diese Datei prüft die
Auflösung **in einer nachgestellten Container-Anordnung** — die echte lässt sich hier
nicht herstellen, die Entwicklungsumgebung hat keinen Docker.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from app.core.paths import aufloesen

REPO = Path(__file__).resolve().parents[3]
APP = REPO / "backend" / "app"
COMPOSE = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
DIENSTE = ("backend", "cron")

# Einstellung → Ort im Container. Die Compose übergibt diese Pfade zusätzlich absolut:
# doppelt gemoppelt, aber der Ausfall wäre still, und die Variablen sind ohnehin der
# dokumentierte Weg, eine Datei woanders hinzulegen (docs/admin/konfiguration.md).
ABSOLUT_UEBERGEBEN = {
    "PEDAGOGY_PATH": "/app/config/pedagogy.yaml",
    "CRISIS_TRIGGERS_PATH": "/app/config/crisis_triggers.yaml",
    "HELP_RESOURCES_PATH": "/app/config/help_resources.yaml",
    "IMAGE_MODELS_PATH": "/app/config/image_models.yaml",
    "IMAGE_BLOCKLIST_PATH": "/app/config/image_blocklist.yaml",
    "GUARDRAIL_HEALTH_FILE": "/app/data/guardrail_health.json",
}


# ── Die Auflösung selbst ─────────────────────────────────────────────────────


def _layout(wurzel: Path, *, mit_backend_ebene: bool, dateien: tuple[str, ...]) -> Path:
    """Baut eine der beiden Anordnungen nach und gibt das Paketverzeichnis zurück.

    `mit_backend_ebene=True` ist der Entwicklungsbaum (`<repo>/backend/app`), `False` der
    Container (`/app/app`). Die Konfigurationsdateien landen jeweils dort, wo sie in der
    echten Anordnung liegen.
    """
    basis = wurzel / "backend" if mit_backend_ebene else wurzel
    paket = basis / "app" / "core"
    paket.mkdir(parents=True)
    # Echte Pakete, keine Namensraum-Pakete: Sonst verschmilzt Python das nachgestellte
    # `app` mit dem echten aus dem Arbeitsverzeichnis, und der Test prüft sich selbst.
    (basis / "app" / "__init__.py").write_text("", encoding="utf-8")
    (paket / "__init__.py").write_text("", encoding="utf-8")
    (paket / "paths.py").write_text(
        (Path(__file__).resolve().parents[2] / "app" / "core" / "paths.py").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    for datei in dateien:
        ziel = wurzel / datei
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_text("x", encoding="utf-8")
    return paket


def _aufloesen_in(paket: Path, pfad: str) -> str:
    """Ruft `aufloesen` in der nachgestellten Anordnung auf — in eigenem Prozess.

    Nötig, weil das Modul seine Kandidaten beim Import aus `__file__` ableitet; ein
    zweiter Import im selben Prozess bekäme die Kandidaten dieser Testumgebung.
    """
    ergebnis = subprocess.run(
        [sys.executable, "-c",
         "from app.core.paths import aufloesen; print(aufloesen(%r))" % pfad],
        # `cwd` statt sys.path-Eintrag: Das echte Backend-Verzeichnis darf gar nicht erst
        # im Suchpfad stehen, sonst gewinnt das dortige `app`-Paket.
        cwd=str(paket.parents[1]),
        env={"PYTHONPATH": "", "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, check=True,
    )
    return ergebnis.stdout.strip()


def test_entwicklungsbaum_verankert_in_der_repo_wurzel(tmp_path):
    """`<repo>/backend/app/…` → `<repo>/config/…`, nicht `<repo>/backend/config/…`.

    Die Unterscheidung ist nicht theoretisch: `backend/config/` existiert (mit
    `assistant_schema.json`). Eine Suche, die beim ersten `config/` haltmacht, bliebe hier
    eine Ebene zu tief hängen.
    """
    paket = _layout(
        tmp_path, mit_backend_ebene=True,
        dateien=("docker-compose.yml", "config/pedagogy.yaml", "backend/config/assistant_schema.json"),
    )
    assert _aufloesen_in(paket, "config/pedagogy.yaml") == str(tmp_path / "config" / "pedagogy.yaml")


def test_container_verankert_neben_dem_paket(tmp_path):
    """`/app/app/…` → `/app/config/…`. Genau der Fall, der auf Prod fehlschlug."""
    paket = _layout(tmp_path, mit_backend_ebene=False, dateien=("config/pedagogy.yaml",))
    assert _aufloesen_in(paket, "config/pedagogy.yaml") == str(tmp_path / "config" / "pedagogy.yaml")


def test_noch_nicht_angelegtes_verzeichnis_im_entwicklungsbaum(tmp_path):
    """Ablageverzeichnisse entstehen erst beim ersten Schreiben — die Anordnung entscheidet.

    Ohne feste Regel landete `data/artifacts` unter `backend/data/artifacts` und damit
    woanders als beim Cron, der aus einem anderen Verzeichnis startet.
    """
    paket = _layout(tmp_path, mit_backend_ebene=True, dateien=("docker-compose.yml",))
    assert _aufloesen_in(paket, "data/artifacts") == str(tmp_path / "data" / "artifacts")


def test_noch_nicht_angelegtes_verzeichnis_im_container(tmp_path):
    """Im Container gibt es keine docker-compose.yml — dann gilt das Paket-Elternverzeichnis."""
    paket = _layout(tmp_path, mit_backend_ebene=False, dateien=())
    assert _aufloesen_in(paket, "data/artifacts") == str(tmp_path / "data" / "artifacts")


def test_herumliegendes_verzeichnis_aendert_nichts(tmp_path):
    """Ein `backend/data/` aus einem früheren Lauf darf die Wurzel nicht verschieben.

    Der erste Entwurf nahm „die Wurzel, unter der der Pfad existiert" — und lieferte
    dadurch auf einem Rechner mit Altbestand ein anderes Ergebnis als auf einem frischen.
    """
    paket = _layout(
        tmp_path, mit_backend_ebene=True,
        dateien=("docker-compose.yml", "backend/data/artifacts/alt.svg"),
    )
    assert _aufloesen_in(paket, "data/artifacts") == str(tmp_path / "data" / "artifacts")


def test_absoluter_pfad_bleibt_unberuehrt():
    assert aufloesen("/etc/irgendwo.yaml") == Path("/etc/irgendwo.yaml")


def test_bestehende_config_wird_hier_gefunden():
    """Gegenprobe in der echten Umgebung: Die Datei liegt in der Repo-Wurzel."""
    assert aufloesen("config/pedagogy.example.yaml") == REPO / "config" / "pedagogy.example.yaml"


# ── Rückfallschutz ───────────────────────────────────────────────────────────


def test_kein_modul_rechnet_die_wurzel_noch_selbst_aus():
    """Der eigentliche Regressionsschutz.

    Jede Rechnung von Hand ist eine Gelegenheit, sich um eine Ebene zu vertun — genau das
    war der Fehler, und in `api/admin/guardrail.py` stand er als `parents[4]` neben
    `parents[3]` in den übrigen. Wer eine neue braucht, ergänzt `app/core/paths.py`.
    """
    treffer = []
    for datei in sorted(APP.rglob("*.py")):
        if "__pycache__" in datei.parts or datei.name == "paths.py":
            continue
        quelle = datei.read_text(encoding="utf-8")
        if re.search(r"Path\(__file__\)\.resolve\(\)\.parents\[[2-9]\]", quelle):
            treffer.append(str(datei.relative_to(APP)))

    assert treffer == [], (
        f"Diese Module berechnen ihre Wurzel selbst: {treffer}. Im Container fehlt "
        f"gegenüber dem Entwicklungsbaum die Ebene `backend/` — die Rechnung geht dort "
        f"um eins daneben. Stattdessen `app.core.paths.aufloesen` verwenden."
    )


@pytest.mark.parametrize("dienst", DIENSTE)
@pytest.mark.parametrize("variable,erwartet", sorted(ABSOLUT_UEBERGEBEN.items()))
def test_pfad_wird_zusaetzlich_absolut_uebergeben(dienst, variable, erwartet):
    """Gürtel und Hosenträger: Die Auflösung ist repariert, die Übergabe bleibt.

    Sie kostet nichts, macht im Container sichtbar, wo die Dateien liegen, und trägt
    weiter, falls jemand das Layout erneut verschiebt. Ein Ausfall wäre still — das ist
    der Grund, hier nicht auf eine einzige Absicherung zu setzen.
    """
    gesetzt = COMPOSE["services"][dienst].get("environment", {}).get(variable)
    assert gesetzt == erwartet, (
        f"Dienst '{dienst}': {variable} fehlt oder ist falsch ({gesetzt!r})."
    )
