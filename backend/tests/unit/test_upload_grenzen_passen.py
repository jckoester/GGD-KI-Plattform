"""Die Obergrenze am Proxy muss über den Grenzen der Anwendung liegen (Paket 10, AP3).

Zwei Zahlen an zwei Orten, die dasselbe Ereignis begrenzen: `client_max_body_size` im
nginx und `UPLOAD_MAX_BYTES` / `FACHBEGRIFFE_IMPORT_MAX_BYTES` im Backend. Läuft der
Proxy vor, **antwortet er zuerst** — mit einem nackten 413 ohne Text. Die Fachschaft
sieht dann „Request Entity Too Large" und erfährt weder, was zu groß war, noch wie groß
es sein darf; die sorgfältig formulierte Meldung des Backends erreicht sie nie.

⚠️ **Das ist kein theoretischer Fall.** Vor dem 27.09.2026 stand im nginx 12m und im
Upload-Modul 20 MB — die Hälfte des erlaubten Bündels wäre am Proxy hängen geblieben,
und nichts hätte es angezeigt.

Was hier **nicht** geprüft werden kann: ob envsubst die Vorlage wirklich richtig füllt.
Dafür braucht es einen laufenden Container; die Entwicklungsumgebung hat keinen Docker.
Geprüft wird deshalb die Verdrahtung: dass die Vorlage einen Platzhalter benutzt, dass
die Compose ihn immer setzt und dass der Filter gesetzt ist, ohne den envsubst auch
`$host` und `$upstream_backend` leeren würde.
"""
import os
import re
from pathlib import Path

import pytest
import yaml

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")

from app.config import Settings

REPO = Path(__file__).resolve().parents[3]
COMPOSE = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
VORLAGE = (REPO / "infra" / "nginx.conf.template").read_text(encoding="utf-8")

_EINHEITEN = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3}


def _bytes(wert: str) -> int:
    """nginx-Größenangabe → Bytes. `24m` → 25165824."""
    treffer = re.fullmatch(r"(\d+)([kKmMgG]?)", wert.strip())
    assert treffer, f"„{wert}“ ist keine nginx-Größenangabe"
    return int(treffer.group(1)) * _EINHEITEN[treffer.group(2).lower()]


@pytest.fixture(scope="module")
def proxy_grenze() -> int:
    """Der Vorgabewert aus der Compose — das, was ohne eigene `.env` gilt."""
    umgebung = COMPOSE["services"]["nginx"]["environment"]
    roh = str(umgebung["NGINX_MAX_BODY_SIZE"])
    treffer = re.fullmatch(r"\$\{NGINX_MAX_BODY_SIZE:-(.+)\}", roh)
    assert treffer, (
        "NGINX_MAX_BODY_SIZE braucht einen Vorgabewert in der Compose. Ohne ihn "
        "bliebe der Platzhalter in der Vorlage stehen und nginx startete nicht."
    )
    return _bytes(treffer.group(1))


@pytest.fixture(scope="module")
def einstellungen() -> Settings:
    return Settings()


class TestDerProxyLaesstAllesDurchWasDieAnwendungAnnimmt:
    def test_fachbegriff_import(self, proxy_grenze, einstellungen):
        assert proxy_grenze >= einstellungen.fachbegriffe_import_max_bytes, (
            "NGINX_MAX_BODY_SIZE ist kleiner als FACHBEGRIFFE_IMPORT_MAX_BYTES — "
            "Bündel dazwischen enden mit einem nackten 413 vom Proxy."
        )

    def test_chat_anhaenge(self, proxy_grenze, einstellungen):
        assert proxy_grenze >= einstellungen.upload_max_bytes

    def test_mit_puffer_fuer_den_umschlag(self, proxy_grenze, einstellungen):
        """`multipart/form-data` schickt mehr als die Nutzlast: Trennzeichen, Kopfzeilen
        je Teil, und ein Bündel besteht aus vielen Teilen. Wäre der Proxy genau so groß
        wie die Anwendungsgrenze, fiele das größte erlaubte Bündel trotzdem durch."""
        assert proxy_grenze >= einstellungen.fachbegriffe_import_max_bytes * 1.1


class TestVerdrahtung:
    def test_die_vorlage_hat_keine_feste_zahl(self):
        assert "${NGINX_MAX_BODY_SIZE}" in VORLAGE
        assert not re.search(r"client_max_body_size\s+\d", VORLAGE), (
            "Eine feste Zahl in der Vorlage gewänne gegen jede Einstellung."
        )

    def test_die_vorlage_wird_als_vorlage_gemountet(self):
        ziele = [
            v.split(":")[1] for v in COMPOSE["services"]["nginx"]["volumes"]
        ]
        assert any(z.startswith("/etc/nginx/templates/") for z in ziele), (
            "Nur unter /etc/nginx/templates/ füllt der Einstiegspunkt die Vorlage. "
            "Unter conf.d/ landete der Platzhalter unverändert in der Konfiguration."
        )

    def test_der_envsubst_filter_steht(self):
        """⚠️ Ohne ihn ersetzte envsubst auch `$host` und `$upstream_backend` durch
        Leerzeichenketten — die Konfiguration wäre syntaktisch heil und kaputt."""
        umgebung = COMPOSE["services"]["nginx"]["environment"]
        assert umgebung.get("NGINX_ENVSUBST_FILTER") == "NGINX_"

    def test_die_nginx_variablen_heissen_nicht_versehentlich_nginx(self):
        """Gegenprobe zum Filter: Trüge eine nginx-eigene Variable das Präfix `NGINX_`,
        ersetzte envsubst sie doch — und der Filter schützte nichts mehr."""
        eigene = set(re.findall(r"\$(\w+)", VORLAGE)) - {"NGINX_MAX_BODY_SIZE"}
        assert not [v for v in eigene if v.startswith("NGINX_")], sorted(eigene)
