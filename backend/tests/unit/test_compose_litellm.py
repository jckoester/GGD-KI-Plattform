"""Release 0.7.0 Schritt 7 — LiteLLM als Dienst der Anwendungs-Compose.

Der Umzug macht aus zwei getrennten Konfigurationen eine. Der Gewinn ist, dass
Zusammengehöriges zusammen versioniert wird; die neue Gefahr ist, dass es an mehreren
Stellen **wiederholt** wird: Der Pfad der Guardrail-Zählerdatei steht in der .env und in
zwei Config-Vorlagen, der Modulpfad der Guardrails hängt an einem Mountpunkt, und die
Proxy-Version steht in der Compose und im Pin für die Dev-venv.

Solche Wiederholungen laufen leise auseinander — nichts stürzt ab, es wird nur nicht mehr
geprüft, gezählt oder gefunden. Diese Datei hält sie gegeneinander.

Was hier NICHT geprüft werden kann: ob der Stack läuft. Dafür gibt es die Abnahmeliste in
docs/runbooks/litellm-in-die-compose.md.
"""
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
COMPOSE = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
ENV_EXAMPLE = (REPO / ".env.example").read_text(encoding="utf-8")
CONFIG_VORLAGEN = [
    REPO / "infra" / "litellm_config.example.yaml",
    REPO / "infra" / "litellm_config.ionos.example.yaml",
]


@pytest.fixture(scope="module")
def dienst() -> dict:
    assert "litellm" in COMPOSE["services"], (
        "Der Proxy gehört in dieselbe Compose wie die Anwendung (Release 0.7.0, Punkt 7)."
    )
    return COMPOSE["services"]["litellm"]


def _env_wert(name: str) -> str:
    treffer = re.search(rf"^{name}=(.*)$", ENV_EXAMPLE, re.MULTILINE)
    assert treffer, f"{name} fehlt in .env.example"
    return treffer.group(1).split("#")[0].strip()


def _mounts(dienst: dict) -> dict[str, str]:
    """Bind-Mounts als {Host-Pfad: Container-Pfad}, ohne Modus-Suffix."""
    paare = {}
    for eintrag in dienst.get("volumes", []):
        host, _, rest = eintrag.partition(":")
        ziel = rest.split(":")[0]
        paare[host] = ziel
    return paare


# ── Version: eine Fassung in dev und Produktion ──────────────────────────────


def test_image_version_entspricht_dem_pin_der_dev_venv(dienst):
    """Sonst entwickelt man gegen eine andere Fassung, als produktiv läuft.

    Das trifft besonders die Guardrail-Konfiguration: Ihre Syntax hat sich zwischen
    LiteLLM-Versionen schon geändert (der Typ `regex` ist ersatzlos entfallen), und ein
    Proxy, der damit nicht startet, fällt lokal nicht auf, wenn dort eine ältere Fassung
    läuft.
    """
    pin = re.search(
        r"^litellm\[proxy\]==([\d.]+)",
        (REPO / "infra" / "litellm-requirements.txt").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert pin, "Versions-Pin in infra/litellm-requirements.txt nicht gefunden"

    assert pin.group(1) in dienst["image"], (
        f"Image {dienst['image']} und Pin {pin.group(1)} laufen auseinander. "
        f"Ein Upgrade ändert BEIDE Stellen."
    )


# ── Die Datenbank des Proxys ist nicht die der Anwendung ─────────────────────


def test_datenbankadresse_wird_am_dienst_ueberschrieben(dienst):
    """Der Proxy darf DATABASE_URL nicht aus der .env erben.

    Er bindet dieselbe .env ein wie das Backend; dort steht der asyncpg-DSN der
    ANWENDUNG. `general_settings.database_url` aus der Config gewinnt zwar im
    Normalpfad, aber nicht jeder Startpfad liest die Config
    (litellm/proxy/prisma_migration.py ruft den Server ohne `--config` auf).

    Der schlechte Ausgang wäre kein Absturz, sondern LiteLLMs Prisma-Schema in `ggd_ki`.
    """
    umgebung = dienst.get("environment", {})
    assert umgebung.get("DATABASE_URL") == "${LITELLM_DATABASE_URL}", (
        "Der litellm-Dienst muss DATABASE_URL ausdrücklich auf LITELLM_DATABASE_URL "
        "setzen — sonst erbt er die Adresse der Anwendungsdatenbank aus der .env."
    )


def test_getrennte_datenbanken_in_der_env_vorlage():
    """Zwei Adressen, zwei Datenbanknamen — und der Proxy ohne asyncpg-Treiber."""
    app_dsn = _env_wert("DATABASE_URL")
    proxy_dsn = _env_wert("LITELLM_DATABASE_URL")

    assert app_dsn != proxy_dsn
    assert "+asyncpg" not in proxy_dsn, "LiteLLM/Prisma versteht den asyncpg-DSN nicht."
    assert app_dsn.rsplit("/", 1)[-1] != proxy_dsn.rsplit("/", 1)[-1], (
        "Prisma-Schema und Alembic-Schema gehören in getrennte Datenbanken."
    )


def test_datenbank_wird_bei_neuinstallation_angelegt():
    """Prisma migriert in eine vorhandene Datenbank — anlegen kann es sie nicht.

    Ohne das Init-Verzeichnis am db-Dienst startet eine Neuinstallation mit einem
    Proxy in der Neustartschleife.
    """
    assert (REPO / "infra" / "db-init" / "10-litellm-db.sh").exists()
    assert "./infra/db-init" in _mounts(COMPOSE["services"]["db"])


# ── Guardrails: Modulpfad und Zählerdatei ────────────────────────────────────


def test_guardrail_modulpfad_deckt_sich_mit_dem_mount(dienst):
    """Der Modulname in der Config ist ein DATEIPFAD ab dem Arbeitsverzeichnis.

    Das Image arbeitet in /app. Liegt das Guardrail-Verzeichnis woanders, findet
    LiteLLM `guardrails.llm_moderation` nicht — und der Jugendschutz ist aus, ohne dass
    der Proxy deswegen stehenbliebe.
    """
    ziel = _mounts(dienst).get("./infra/guardrails")
    assert ziel == "/app/guardrails", (
        "infra/guardrails muss nach /app/guardrails eingehängt sein, damit der Modulpfad "
        "`guardrails.llm_moderation.…` aus den Config-Vorlagen aufgeht."
    )
    # llm_moderation.py importiert seinerseits `moderation_core` — ohne PYTHONPATH
    # scheitert das, obwohl die Datei da ist.
    assert dienst["environment"].get("PYTHONPATH") == "/app/guardrails"

    for vorlage in CONFIG_VORLAGEN:
        assert "guardrails.llm_moderation" in vorlage.read_text(encoding="utf-8")


def test_zaehlerdatei_ist_fuer_beide_seiten_dieselbe(dienst):
    """Der Proxy schreibt sie, das Backend liest sie — über verschiedene Pfade.

    Zeigen sie auseinander, meldet /admin/guardrail/health dauerhaft „kein Bericht".
    Das ist derselbe Zustand wie bei einem ausgefallenen Guardrail und deshalb nicht
    als Konfigurationsfehler erkennbar.
    """
    vom_backend = _env_wert("GUARDRAIL_HEALTH_FILE")           # data/guardrail_health.json
    assert vom_backend.startswith("data/")

    im_container = "/app/" + vom_backend
    for vorlage in CONFIG_VORLAGEN:
        assert f'health_file: "{im_container}"' in vorlage.read_text(encoding="utf-8"), (
            f"{vorlage.name} muss {im_container} als health_file führen — das ist die "
            f"Datei, die GUARDRAIL_HEALTH_FILE={vom_backend} im Backend meint."
        )

    for name in ("litellm", "backend", "cron"):
        assert _mounts(COMPOSE["services"][name]).get("./data") == "/app/data", (
            f"Dienst '{name}' muss ./data einbinden, sonst treffen sich die beiden "
            f"Seiten der Zählerdatei nicht."
        )


# ── Erreichbarkeit ───────────────────────────────────────────────────────────


def test_proxy_port_ist_nicht_oeffentlich(dienst):
    """Die Proxy-UI ist mit dem Master-Key gleichbedeutend mit Vollzugriff.

    Ein `4000:4000` veröffentlichte Schlüsselverwaltung und Budgets im Netz.
    """
    for eintrag in dienst.get("ports", []):
        assert str(eintrag).startswith("127.0.0.1:"), (
            f"Port-Freigabe '{eintrag}' ist nicht auf localhost beschränkt. "
            f"Zugriff auf die Proxy-UI gehört über einen SSH-Tunnel."
        )


def test_backend_wartet_nicht_auf_den_proxy():
    """Bewusste Entkopplung — hier festgehalten, damit sie nicht „reparariert" wird.

    Der Proxy wird zur Laufzeit gebraucht, nicht beim Start. Ein Wartezwang hieße, dass
    ein gestörter Anbieterzugang auch Anmeldung, Historie und Verwaltung stumm legt.
    """
    assert "litellm" not in COMPOSE["services"]["backend"].get("depends_on", {})


def test_proxy_wartet_auf_die_datenbank(dienst):
    assert dienst["depends_on"]["db"]["condition"] == "service_healthy"
