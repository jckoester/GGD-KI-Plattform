"""Step-up-Re-Authentifizierung (Krisen-Einsicht Phase 12, Schritt 5 — D1).

Sensible Aktionen (Einsicht beantragen-Freigabe, Reader-View) verlangen eine *frische*
Authentifizierung — nicht nur ein gültiges 30-Tage-Session-JWT. Step-up ist eine
Adapter-Fähigkeit (redirect: OAuth `prompt=login` + `auth_time`; direct: Passwort-
Re-Entry), der gemeinsame Nenner ist ein **separates, kurzlebiges Step-up-Token**
(eigenes `stepup`-Cookie). Das Session-JWT wird dabei nie verändert.
"""

import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from jose import JWTError, jwt

# Erlaubte Step-up-Aktionen (an den `action`-Claim gebunden). Neue sensible Aktion → hier
# ergänzen und einen `require_fresh_stepup_for(...)`-Guard setzen.
ALLOWED_STEPUP_ACTIONS = frozenset({"approve", "deny", "read", "export"})

# Gültigkeitsdauer des Step-up-Tokens (Zeitfenster für die sensible Aktion).
STEPUP_TTL_SECONDS = 300  # 5 Minuten
# Maximales Alter der IdP-`auth_time` im Redirect-Pfad (Frische-Sicherheitsnetz:
# honoriert der IdP `prompt=login` nicht, ist auth_time alt → Ablehnung).
STEPUP_AUTH_TIME_MAX_AGE = 120  # 2 Minuten

_STATE_PREFIX = "su."


# ---------- Step-up-Token (separates Cookie, getrennt vom Session-JWT) ----------

def issue_stepup_token(
    secret: str, pseudonym: str, action: str, resource_id: str, algorithm: str = "HS256"
) -> str:
    """Frisches, **einmalig** einlösbares Step-up-Token, gebunden an Aktion + Ressource.

    `jti` erlaubt die Einmalverwendung (Nonce-Store), `action`/`resource_id` binden das
    Token an genau eine sensible Aktion auf genau eine Ressource (kein Cross-Action-Reuse).
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": pseudonym,
        "purpose": "stepup",
        "action": action,
        "resource_id": resource_id,
        "jti": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=STEPUP_TTL_SECONDS)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_stepup_token(token: str, secret: str, algorithm: str = "HS256") -> dict | None:
    """Dekodiert + validiert Signatur/Ablauf/`purpose`. Gibt die Claims zurück oder None.

    Aktions-/Ressourcen-/sub-Abgleich und die Einmalverwendung (jti) macht der Guard
    (`require_fresh_stepup_for`)."""
    try:
        raw = jwt.decode(token, secret, algorithms=[algorithm])
    except JWTError:
        return None
    if raw.get("purpose") != "stepup":
        return None
    return raw


# ---------- Signierter Step-up-State (OAuth-Redirect-Pfad, an sub gebunden) ----------

def _b64(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _unb64(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding).decode()


def _state_sig(secret: str, payload: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def sign_stepup_state(
    secret: str, sub: str, return_to: str, nonce: str, action: str, resource_id: str
) -> str:
    """Signierter State `su.<sub>.<b64(return_to)>.<nonce>.<action>.<resource_id>.<sig>`.

    `action`/`resource_id` reisen mitsigniert durch den OAuth-Redirect, damit der Callback
    das Step-up-Token an dieselbe Aktion/Ressource binden kann (Redirect-Pfad, Audit #3)."""
    payload = f"{_STATE_PREFIX}{sub}.{_b64(return_to)}.{nonce}.{action}.{resource_id}"
    return f"{payload}.{_state_sig(secret, payload)}"


def is_stepup_state(state: str | None) -> bool:
    return bool(state) and state.startswith(_STATE_PREFIX)


def parse_stepup_state(secret: str, state: str) -> tuple[str, str, str, str] | None:
    """Verifiziert Signatur, gibt (sub, return_to, action, resource_id) oder None."""
    if not is_stepup_state(state):
        return None
    parts = state.split(".")
    if len(parts) != 7:
        return None
    _, sub, rt_b64, nonce, action, resource_id, sig = parts
    payload = f"{_STATE_PREFIX}{sub}.{rt_b64}.{nonce}.{action}.{resource_id}"
    if not hmac.compare_digest(_state_sig(secret, payload), sig):
        return None
    try:
        return_to = _unb64(rt_b64)
    except Exception:
        return None
    return sub, return_to, action, resource_id


# ---------- auth_time-Frische (Redirect-Pfad) ----------

def auth_time_is_fresh(auth_time: int | None, now_ts: int) -> bool:
    """True, wenn die IdP-Authentifizierung innerhalb des Frische-Fensters liegt."""
    if auth_time is None:
        return False
    return 0 <= (now_ts - auth_time) <= STEPUP_AUTH_TIME_MAX_AGE
