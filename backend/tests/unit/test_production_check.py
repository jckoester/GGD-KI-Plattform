"""Betriebsprüfung — die Werte, die nur auf Produktion gesetzt werden können.

Der Sicherheits-Audit ist im Code abgearbeitet (#1–#18). Was offen bleibt, sind
Einstellungen, deren Fehlen **nichts auslöst**: `ALLOWED_HOSTS` auf `*` heißt Host-Schutz
aus, ein Loopback-`TRUSTED_PROXIES` hinter einem Container-Proxy heißt falsche IP in jeder
Audit-Zeile. Genau diese Stillen prüft `pruefe_produktion`.

Jeder Test beschreibt, **was ohne den Befund passiert wäre** — sonst ist in einem Jahr
nicht mehr erkennbar, warum eine Warnung Warnung ist und ein Fehler Fehler.
"""
from datetime import date
from types import SimpleNamespace

import pytest

from app.core.production_check import ERROR, WARNING, pruefe_produktion


def _settings(**over):
    """Eine tadellose Produktionskonfiguration — jeder Test bricht genau eine Sache."""
    basis = dict(
        environment="production",
        school_secret="x" * 40,
        jwt_secret="y" * 40,
        litellm_master_key="sk-" + "z" * 30,
        allowed_hosts=["ki.beispielschule.de"],
        frontend_origin="https://ki.beispielschule.de",
        trusted_proxies=["172.16.0.0/12"],
        auth_debug_userinfo=False,
        litellm_proxy_url="http://litellm:4000",
    )
    basis.update(over)
    return SimpleNamespace(**basis)


def _auth(**over):
    basis = dict(
        adapter="oauth",
        oauth={"jwks_url": "https://schule.example/idp/jwks"},
        group_role_map_dict={"admins": "admin", "kollegium": "teacher", "sozial": "review"},
    )
    basis.update(over)
    return SimpleNamespace(**basis)


def _schuljahr(beginn=date(2026, 9, 14), ende=date(2027, 7, 28)):
    return SimpleNamespace(schuljahr="2026/27", beginn=beginn, ende=ende)


def _texte(befunde, level=None):
    return " | ".join(b.message for b in befunde if level is None or b.level == level)


def test_saubere_konfiguration_meldet_nichts():
    """Die Gegenprobe zu allem Folgenden — sonst prüfte die Suite nur ihre eigenen Fehler."""
    befunde = pruefe_produktion(
        _settings(), _auth(), _schuljahr(), heute=date(2026, 9, 20)
    )
    assert befunde == [], _texte(befunde)


# ── Betriebsmodus und Secrets (Audit #7, #9) ─────────────────────────────────


def test_entwicklungsmodus_ist_ein_fehler():
    """`development` schaltet die Secret-Prüfung ab und Cookies ohne `secure`."""
    befunde = pruefe_produktion(_settings(environment="development"))
    assert "ENVIRONMENT" in _texte(befunde, ERROR)


@pytest.mark.parametrize(
    "feld,wert",
    [
        ("school_secret", "changeme"),
        ("jwt_secret", "kurz"),
        ("litellm_master_key", "sk-1234"),
    ],
)
def test_platzhalter_und_kurze_secrets(feld, wert):
    befunde = pruefe_produktion(_settings(**{feld: wert}))
    assert feld.upper() in _texte(befunde, ERROR)


# ── Host-Header (Audit #18) ──────────────────────────────────────────────────


def test_offener_host_header_ist_eine_warnung():
    """Kein Fehler — der Reverse-Proxy bleibt die primäre Absicherung."""
    befunde = pruefe_produktion(_settings(allowed_hosts=["*"]))
    assert "ALLOWED_HOSTS" in _texte(befunde, WARNING)


def test_eigener_hostname_fehlt_in_der_allowlist():
    """Der teure Fall: Die Plattform weist ihre eigene Adresse mit 400 ab.

    Deshalb Fehler und nicht Warnung — hier ist nicht der Schutz aus, sondern die
    Anwendung unerreichbar.
    """
    befunde = pruefe_produktion(
        _settings(allowed_hosts=["alt.beispielschule.de"],
                  frontend_origin="https://ki.beispielschule.de")
    )
    assert "ki.beispielschule.de" in _texte(befunde, ERROR)


# ── Audit-IP hinter dem Proxy (Audit #13) ────────────────────────────────────


def test_loopback_proxies_im_containerbetrieb():
    """Der Peer ist der nginx-Container, nicht 127.0.0.1.

    Mit Loopback-Vorgabe wird `X-Forwarded-For` verworfen — und im Audit-Log steht für
    **jede** Anfrage die Adresse des Proxys. Forensisch wertlos, ohne dass etwas
    fehlschlägt.
    """
    befunde = pruefe_produktion(_settings(trusted_proxies=["127.0.0.1", "::1"]))
    assert "TRUSTED_PROXIES" in _texte(befunde, WARNING)


def test_echtes_proxynetz_ist_in_ordnung():
    assert pruefe_produktion(_settings(trusted_proxies=["172.16.0.0/12"])) == []


def test_im_entwicklungsmodus_keine_proxy_warnung():
    """Lokal ist Loopback richtig — die Warnung gälte dort immer und würde stumpf."""
    befunde = pruefe_produktion(_settings(environment="development",
                                          trusted_proxies=["127.0.0.1"]))
    assert "TRUSTED_PROXIES" not in _texte(befunde)


# ── Anmeldung ────────────────────────────────────────────────────────────────


def test_pii_debugflag(monkeypatch):
    """Audit #15: schreibt bei jedem Login Klarnamen ins Log."""
    befunde = pruefe_produktion(_settings(auth_debug_userinfo=True))
    assert "AUTH_DEBUG_USERINFO" in _texte(befunde, ERROR)


def test_testadapter_in_produktion():
    befunde = pruefe_produktion(_settings(), _auth(adapter="yaml_test", oauth={}))
    assert "yaml_test" in _texte(befunde, ERROR)


def test_fehlende_jwks_url():
    """Audit #6 — ohne sie bleibt die ID-Token-Signatur ungeprüft."""
    befunde = pruefe_produktion(_settings(), _auth(oauth={}))
    assert "jwks_url" in _texte(befunde, ERROR)


def test_ohne_review_zuordnung_laeuft_das_vier_augen_prinzip_leer():
    befunde = pruefe_produktion(
        _settings(), _auth(group_role_map_dict={"admins": "admin"})
    )
    assert "review" in _texte(befunde, WARNING)


# ── Proxy-Adresse und Schuljahr ──────────────────────────────────────────────


def test_proxy_auf_localhost():
    """Im Container ist das die Anwendung selbst — jeder Chat scheitert."""
    befunde = pruefe_produktion(_settings(litellm_proxy_url="http://localhost:4000"))
    assert "LITELLM_PROXY_URL" in _texte(befunde, ERROR)


def test_schuljahr_abgelaufen():
    """Der Produktivfall vom 30.08.2026: Config führt noch 2025/26.

    Folge: Der Zuteilungslauf findet nie eine Unterrichtswoche, Budgets wachsen nicht,
    der Jahreswechsel-Reset löst nicht aus.
    """
    befunde = pruefe_produktion(
        _settings(), _auth(),
        _schuljahr(beginn=date(2025, 9, 15), ende=date(2026, 7, 29)),
        heute=date(2026, 8, 31),
    )
    assert "außerhalb des konfigurierten Schuljahres" in _texte(befunde, ERROR)


def test_ferien_im_laufenden_schuljahr_sind_kein_befund():
    """Nur außerhalb des Schuljahres ist ein Fehler — Ferien sind Normalbetrieb."""
    befunde = pruefe_produktion(
        _settings(), _auth(), _schuljahr(), heute=date(2026, 12, 24)
    )
    assert befunde == [], _texte(befunde)


def test_ohne_optionale_quellen_laeuft_die_pruefung_durch():
    """auth.yaml oder school_year.yaml unlesbar: Die übrigen Prüfungen sollen greifen."""
    assert pruefe_produktion(_settings(), None, None) == []
