"""Verschlüsselung der Zugangsdaten in `calendar_sources.config` (ADR-006).

Warum überhaupt: Anders als die übrigen Geheimnisse der Plattform steht dieses **in der
Datenbank**, nicht in der Umgebung. Ein WebUntis-Dienstpasswort im Klartext in einer Spalte
läge in jedem Backup, jedem Dump und jeder Fehlermeldung, die eine Zeile ausgibt. Der
Schlüssel dagegen bleibt in der Umgebung — wer nur die Datenbank hat, hat nichts.

Verfahren: Fernet (AES-128-CBC + HMAC-SHA256, authentifiziert). Der Schlüssel wird per
HKDF aus `SCHOOL_SECRET` abgeleitet, damit keine weitere Variable zu verwalten ist. Das
Kontext-Label bindet ihn an diesen Zweck: Derselbe Schulschlüssel ergibt für einen anderen
Zweck einen anderen Fernet-Schlüssel, sodass Geheimtexte nicht zwischen Bereichen wandern.

**Rotiert die Schule `SCHOOL_SECRET`, sind hiermit verschlüsselte Werte verloren** — das ist
gewollt und harmlos: Sie werden neu eingetragen, nicht wiederhergestellt. Eine Rotation
verändert aber auch alle Pseudonyme, ist also ohnehin ein schwerer Eingriff.
"""
from __future__ import annotations

import base64
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import settings

# Zweckbindung der Schlüsselableitung. Nicht ändern — sonst werden bestehende
# Geheimtexte unlesbar.
_KDF_INFO = b"ggd-ki-plattform/calendar-source-config/v1"

# Schlüssel, deren Werte als Geheimnis gelten. Alles andere in `config` bleibt Klartext,
# damit die Verbindungsparameter les- und prüfbar bleiben.
#
# `url` steht bewusst mit drin: Eine ICS-Abo-URL **ist** das Geheimnis — wer sie hat, liest
# den Plan. Der WebUntis-Servername ist dagegen keins und heißt deshalb `server`, nicht
# `url`; er bleibt lesbar, was die Fehlersuche erheblich erleichtert.
SECRET_KEYS = frozenset({"password", "passwort", "token", "secret", "url", "api_key"})

# Präfix der verschlüsselten Werte. Er macht am Wert selbst erkennbar, dass er
# verschlüsselt ist — nötig, um bereits verschlüsselte Werte nicht doppelt zu verpacken.
_PREFIX = "enc:v1:"


class SecretDecryptionError(RuntimeError):
    """Ein gespeicherter Wert ließ sich nicht entschlüsseln."""


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    raw = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_KDF_INFO,
    ).derive(settings.school_secret.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(raw))


def encrypt_value(plaintext: str) -> str:
    """Einen Einzelwert verschlüsseln. Bereits verschlüsselte Werte bleiben unverändert."""
    if plaintext.startswith(_PREFIX):
        return plaintext
    return _PREFIX + _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_value(stored: str) -> str:
    """Einen Einzelwert entschlüsseln. Werte ohne Präfix werden durchgereicht.

    Das Durchreichen ist bewusst: Es erlaubt, eine bestehende Zeile mit Klartext-Wert zu
    lesen und beim nächsten Speichern zu verschlüsseln, ohne Migrationsschritt.
    """
    if not stored.startswith(_PREFIX):
        return stored
    try:
        return _fernet().decrypt(stored[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        # Bewusst ohne den Geheimtext in der Meldung.
        raise SecretDecryptionError(
            "Zugangsdaten nicht entschlüsselbar — wurde SCHOOL_SECRET geändert?"
        ) from exc


def encrypt_config(config: dict) -> dict:
    """Alle Geheimnis-Schlüssel eines `config`-Dicts verschlüsseln."""
    return {
        key: encrypt_value(value)
        if key.lower() in SECRET_KEYS and isinstance(value, str)
        else value
        for key, value in config.items()
    }


def decrypt_config(config: dict) -> dict:
    """Gegenstück zu `encrypt_config`."""
    return {
        key: decrypt_value(value)
        if key.lower() in SECRET_KEYS and isinstance(value, str)
        else value
        for key, value in config.items()
    }


def redact_config(config: dict) -> dict:
    """Fassung für Anzeige und Protokoll — Geheimnisse durch einen Platzhalter ersetzt.

    Für alles gedacht, was den Server verlässt: API-Antworten, Logzeilen, Fehlertexte.
    Ein gesetztes Geheimnis wird als gesetzt *angezeigt*, ohne es preiszugeben — die
    Unterscheidung „leer" / „gefüllt" ist für die Fehlersuche nötig und selbst harmlos.
    """
    return {
        key: ("<gesetzt>" if value else "")
        if key.lower() in SECRET_KEYS and isinstance(value, str)
        else value
        for key, value in config.items()
    }
