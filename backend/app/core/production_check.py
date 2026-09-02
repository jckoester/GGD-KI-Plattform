"""Betriebswerte gegen die Anforderungen des Sicherheits-Audits prüfen.

Der Audit (`Sicherheits-Audit-Plan.md`, #1–#18) ist **im Code** vollständig abgearbeitet.
Was danach offen bleibt, sind Werte, die nur auf der Produktion gesetzt werden können —
und ein Teil davon fällt **still** aus, wenn er fehlt: `ALLOWED_HOSTS` steht auf `*` und
der Host-Schutz ist einfach aus, `TRUSTED_PROXIES` passt nicht zum Netz und die Audit-IP
zeigt auf den Reverse-Proxy statt auf die Nutzer:in. Kein Fehler, keine Meldung.

Diese Prüfung macht daraus eine Ausgabe. Sie ist bewusst **rein lokal**: kein Netz, keine
Datenbank, kein laufender Proxy. Damit läuft sie vor dem ersten Start, im Container und in
der CI gleichermaßen — und was sie nicht beantworten kann, sagt sie (siehe
``NICHT_PRUEFBAR``).

Die Modell- und Preisseite prüft `check_litellm_config.py`; beides zusammen ergibt die
Inbetriebnahme-Prüfung.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional
from urllib.parse import urlparse

ERROR = "error"
WARNING = "warning"
INFO = "info"


@dataclass(frozen=True)
class Befund:
    level: str
    message: str


# Was diese Prüfung grundsätzlich nicht sehen kann — gehört in die Ausgabe, damit ein
# grüner Lauf nicht mit „alles erledigt" verwechselt wird.
NICHT_PRUEFBAR = (
    "Ob die `review`-Rolle tatsächlich vergeben ist (Vier-Augen-Prinzip) — die Zuordnung "
    "steht in der Datenbank: /settings/users, Rollenfilter `review`.",
    "Ob der Reverse-Proxy TLS erzwingt und die Security-Header setzt (Audit #5) — das "
    "steht in der nginx-/Caddy-Konfiguration, nicht hier.",
    "Ob die Secrets nicht doch irgendwo veröffentlicht wurden.",
)


def _ist_platzhalter(wert: str, platzhalter: set[str], mindestlaenge: int) -> bool:
    return len(wert or "") < mindestlaenge or (wert or "").lower() in platzhalter


def pruefe_produktion(
    settings: Any,
    auth_config: Any = None,
    schuljahr: Any = None,
    heute: Optional[date] = None,
) -> list[Befund]:
    """Gleicht die Betriebswerte ab. ``auth_config``/``schuljahr`` optional (dann übersprungen)."""
    from app.config import _MIN_SECRET_LEN, _PLACEHOLDER_MASTER_KEYS, _PLACEHOLDER_SECRETS

    befunde: list[Befund] = []
    ist_produktion = str(getattr(settings, "environment", "")).lower() == "production"

    # ── Betriebsmodus ────────────────────────────────────────────────────────
    if not ist_produktion:
        befunde.append(Befund(
            ERROR,
            f"ENVIRONMENT={getattr(settings, 'environment', '')!r}. In Produktion muss "
            f"'production' stehen: Nur dann werden schwache Secrets beim Start abgelehnt "
            f"und Cookies mit `secure` gesetzt.",
        ))

    # ── Secrets (Audit #7, #9) ───────────────────────────────────────────────
    for name, attr, platzhalter, mindest in (
        ("SCHOOL_SECRET", "school_secret", _PLACEHOLDER_SECRETS, _MIN_SECRET_LEN),
        ("JWT_SECRET", "jwt_secret", _PLACEHOLDER_SECRETS, _MIN_SECRET_LEN),
        ("LITELLM_MASTER_KEY", "litellm_master_key", _PLACEHOLDER_MASTER_KEYS, 20),
    ):
        if _ist_platzhalter(getattr(settings, attr, "") or "", platzhalter, mindest):
            befunde.append(Befund(
                ERROR,
                f"{name} fehlt, ist ein bekannter Platzhalter oder kürzer als {mindest} "
                f"Zeichen. Mit ENVIRONMENT=production startet die Anwendung damit nicht.",
            ))

    # ── Host-Header (Audit #18) ──────────────────────────────────────────────
    hosts = list(getattr(settings, "allowed_hosts", []) or [])
    if not hosts or hosts == ["*"]:
        befunde.append(Befund(
            WARNING,
            "ALLOWED_HOSTS steht auf '*' — der Host-Header-Schutz ist AUS. Kein Fehler, "
            "aber auch keine zweite Verteidigungslinie neben dem Reverse-Proxy. In "
            "Produktion die echten Hostnamen setzen, z. B. [\"ki.beispielschule.de\"].",
        ))
    else:
        origin = str(getattr(settings, "frontend_origin", "") or "")
        host = urlparse(origin).hostname
        if host and host not in hosts:
            befunde.append(Befund(
                ERROR,
                f"FRONTEND_ORIGIN zeigt auf '{host}', ALLOWED_HOSTS kennt diesen Namen "
                f"nicht ({hosts}). Anfragen an die eigene Adresse werden mit 400 "
                f"abgewiesen — die Plattform ist dann nicht erreichbar.",
            ))

    # ── Audit-IP hinter dem Proxy (Audit #13) ────────────────────────────────
    proxies = list(getattr(settings, "trusted_proxies", []) or [])
    if ist_produktion and all(_ist_loopback(p) for p in proxies):
        befunde.append(Befund(
            WARNING,
            f"TRUSTED_PROXIES enthält nur Loopback-Adressen ({proxies}). Im Compose-Betrieb "
            f"ist der direkte Peer aber der nginx-CONTAINER mit einer Adresse aus dem "
            f"Docker-Netz — `X-Forwarded-For` wird dann verworfen, und im Audit-Log steht "
            f"für JEDE Anfrage die Adresse des Proxys statt der Nutzer:in. Das Netz "
            f"eintragen (z. B. [\"172.16.0.0/12\"]) oder die konkrete Container-Adresse.",
        ))

    # ── Anmeldung ────────────────────────────────────────────────────────────
    if getattr(settings, "auth_debug_userinfo", False):
        befunde.append(Befund(
            ERROR,
            "AUTH_DEBUG_USERINFO=true — bei jedem Login werden die vollständigen "
            "SSO-Claims samt Klarnamen ins Log geschrieben (Audit #15). Nur zur "
            "Fehlersuche, nie im Dauerbetrieb.",
        ))

    if auth_config is not None:
        befunde += _pruefe_auth(auth_config, ist_produktion)

    # ── Proxy-Adresse ────────────────────────────────────────────────────────
    proxy_url = str(getattr(settings, "litellm_proxy_url", "") or "")
    if ist_produktion and urlparse(proxy_url).hostname in {"localhost", "127.0.0.1", "::1"}:
        befunde.append(Befund(
            ERROR,
            f"LITELLM_PROXY_URL zeigt auf {proxy_url!r}. Im Container ist das die "
            f"Anwendung selbst — jeder Chat scheitert mit „Connection refused\", während "
            f"alles andere normal aussieht. Im Compose-Betrieb: http://litellm:4000",
        ))

    # ── Schuljahr ────────────────────────────────────────────────────────────
    if schuljahr is not None:
        stichtag = heute or date.today()
        if stichtag < schuljahr.beginn or stichtag > schuljahr.ende:
            befunde.append(Befund(
                ERROR,
                f"Heute ({stichtag}) liegt außerhalb des konfigurierten Schuljahres "
                f"{schuljahr.schuljahr} ({schuljahr.beginn} – {schuljahr.ende}). Der "
                f"wöchentliche Zuteilungslauf findet nie eine Unterrichtswoche: Budgets "
                f"wachsen nicht, der Jahreswechsel-Reset löst nicht aus. "
                f"→ docs/runbooks/schuljahreswechsel.md",
            ))

    # ── Knotentyp-Taxonomie (ADR-018) ────────────────────────────────────────
    # Nur der datenbankfreie Teil — die Prüfung gegen den Bestand braucht eine
    # Verbindung und läuft deshalb beim Start des Backends (`taxonomy_check.py`),
    # nicht hier. Was hier auffällt, verhindert dort ohnehin den Start; diese Ausgabe
    # nimmt den Befund nur vor.
    from app.context.taxonomy_check import pruefe_altlast, pruefe_taxonomie

    for satz in pruefe_taxonomie():
        befunde.append(Befund(
            ERROR,
            f"Taxonomie (app/context/taxonomy.yaml ist Systemdatei, ADR-018): {satz}",
        ))

    altlast = pruefe_altlast()
    if altlast:
        befunde.append(Befund(WARNING, altlast))

    return befunde


def _ist_loopback(eintrag: str) -> bool:
    try:
        return ipaddress.ip_network((eintrag or "").strip(), strict=False).is_loopback
    except ValueError:
        return False


def _pruefe_auth(auth_config: Any, ist_produktion: bool) -> list[Befund]:
    befunde: list[Befund] = []
    adapter = getattr(auth_config, "adapter", None)

    if ist_produktion and adapter == "yaml_test":
        befunde.append(Befund(
            ERROR,
            "Der Auth-Adapter ist `yaml_test` — Anmeldung mit Testkonten aus einer "
            "YAML-Datei, ohne SSO. In Produktion gehört dort `oauth` hin.",
        ))

    if adapter == "oauth" and not (auth_config.oauth or {}).get("jwks_url"):
        befunde.append(Befund(
            ERROR,
            "`oauth.jwks_url` fehlt in auth.yaml — ohne die Adresse kann die Signatur des "
            "ID-Tokens nicht geprüft werden (Audit #6).",
        ))

    rollen = set((getattr(auth_config, "group_role_map_dict", None) or {}).values())
    for rolle, satz in (
        ("admin", "Ohne Zuordnung kommt niemand in die Verwaltung."),
        ("review", "Ohne sie kann kein Einsicht-Antrag zweitfreigegeben werden — das "
                   "Vier-Augen-Prinzip der Krisen-Einsicht läuft leer (Audit #3)."),
    ):
        if rolle not in rollen:
            befunde.append(Befund(
                WARNING,
                f"Keine Gruppe in `group_role_map` bildet auf die Rolle `{rolle}` ab. {satz}",
            ))

    return befunde
