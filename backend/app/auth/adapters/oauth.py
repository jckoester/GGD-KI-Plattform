import base64
import binascii
import hashlib
import hmac
import json
import logging
import re
import secrets
from typing import Literal
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, model_validator

from app.auth.base import AuthAdapter, FreshIdentity, LoginChallenge, NormalizedIdentity
from app.config import Settings

logger = logging.getLogger(__name__)


def _as_str_list(value) -> list[str]:
    """Normalisiert einen userinfo-Claim auf eine Liste von Strings.

    Toleriert: Liste[str] (Standard), Einzel-String, Liste[dict] (Namensfeld wird
    extrahiert). So bricht weder das Matching (`.lower()`) noch die `list[str]`-
    Validierung von NormalizedIdentity, falls ein Provider Gruppen/Rollen als
    Objekte statt als Strings liefert.
    """
    if isinstance(value, str):
        return [value]
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            name = (
                item.get("name")
                or item.get("act")
                or item.get("id")
                or item.get("value")
            )
            if isinstance(name, str):
                out.append(name)
    return out


def _unverified_jwt_claims(token: str) -> dict:
    """Dekodiert die Claims eines JWT **ohne** Signaturprüfung.

    Zulässig nur für das ID-Token aus der Back-Channel-Token-Antwort: es kommt direkt
    vom IdP-Token-Endpunkt über TLS (nicht über den Browser), daher gilt derselbe
    Trust wie für die userinfo-Antwort. Wird ausschließlich gelesen, um `auth_time`
    für die Step-up-Frische zu ermitteln.
    """
    try:
        payload_b64 = token.split(".")[1]
        padding = "=" * (-len(payload_b64) % 4)
        raw = base64.urlsafe_b64decode(payload_b64 + padding)
        return json.loads(raw)
    except (IndexError, binascii.Error, ValueError):
        return {}


class OAuthConfig(BaseModel):
    base_url: str  # z.B. https://iserv.example.de
    client_id: str
    redirect_uri: str
    # OAuth-Scopes. IServ liefert Gruppen-/Rollen-Claims NUR, wenn die jeweiligen
    # Scopes angefordert werden UND der OAuth-Client in IServ dafür freigeschaltet ist.
    # Achtung: IServ benennt diese Scopes mit `iserv:`-Präfix (`iserv:groups`,
    # `iserv:roles`) — `groups`/`roles` ohne Präfix werden mit „scope not allowed"
    # abgelehnt. Bei anderen Providern entsprechend anpassen.
    scope: str = "openid profile email iserv:groups iserv:roles"
    grade_group_pattern: str | None = None
    # Regex mit genau einer Capture-Group, die den Jahrgangswert liefert.
    # Beispiel GGD: "^jahrgang\.(\d{1,2})$"
    # None → Jahrgangs-Erkennung deaktiviert, grade ist immer None
    # client_secret kommt aus Settings (Env-Variable), nicht aus YAML
    # Optionale URL-Overrides; wenn None, werden IServ-Defaults aus base_url abgeleitet
    auth_url: str | None = None
    token_url: str | None = None
    userinfo_url: str | None = None

    @property
    def effective_auth_url(self) -> str:
        return self.auth_url or f"{self.base_url}/iserv/oauth/v2/auth"

    @property
    def effective_token_url(self) -> str:
        return self.token_url or f"{self.base_url}/iserv/oauth/v2/token"

    @property
    def effective_userinfo_url(self) -> str:
        return self.userinfo_url or f"{self.base_url}/iserv/oauth/v2/userinfo"

    @model_validator(mode="after")
    def check_grade_pattern_has_capture_group(self) -> "OAuthConfig":
        if self.grade_group_pattern is not None:
            try:
                compiled = re.compile(self.grade_group_pattern)
            except re.error as e:
                raise ValueError(f"grade_group_pattern ist kein gültiges Regex: {e}")
            if compiled.groups < 1:
                raise ValueError(
                    "grade_group_pattern muss genau eine Capture-Group enthalten"
                )
        return self


class OAuthAdapter(AuthAdapter):
    def __init__(
        self,
        raw: dict,
        settings: Settings,
        group_role_map: dict[str, str] | None = None,
    ) -> None:
        self._config = OAuthConfig.model_validate(raw)
        self._client_secret = settings.auth_iserv_client_secret
        self._school_secret = settings.school_secret
        self._group_role_map = group_role_map or {}
        self._debug_userinfo = settings.auth_debug_userinfo

    @property
    def mode(self) -> Literal["redirect"]:
        return "redirect"

    async def get_login_challenge(self) -> LoginChallenge:
        nonce = secrets.token_urlsafe(16)
        sig = hmac.new(
            self._school_secret.encode(), nonce.encode(), hashlib.sha256
        ).hexdigest()
        state = f"{nonce}.{sig}"
        params = {
            "response_type": "code",
            "client_id": self._config.client_id,
            "redirect_uri": self._config.redirect_uri,
            "scope": self._config.scope,
            "state": state,
        }
        url = f"{self._config.effective_auth_url}?" + urlencode(params)
        return LoginChallenge(type="redirect", redirect_url=url, state=state)

    async def exchange_code(self, code: str, state: str) -> NormalizedIdentity:
        self._verify_state(state)
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                self._config.effective_token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._config.redirect_uri,
                    "client_id": self._config.client_id,
                    "client_secret": self._client_secret,
                },
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]

            userinfo_resp = await client.get(
                self._config.effective_userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            userinfo_resp.raise_for_status()

        return self._userinfo_to_identity(userinfo_resp.json())

    async def authenticate_direct(
        self, username: str, password: str
    ) -> NormalizedIdentity | None:
        raise NotImplementedError("OAuthAdapter unterstützt kein direktes Login")

    async def get_stepup_challenge(self, state: str) -> LoginChallenge:
        # prompt=login + max_age=0 erzwingen eine frische Credential-Eingabe beim IdP.
        # Gleicher redirect_uri wie beim Login → kein zweiter registrierter URI nötig;
        # der Callback unterscheidet Login vs. Step-up am State-Präfix.
        params = {
            "response_type": "code",
            "client_id": self._config.client_id,
            "redirect_uri": self._config.redirect_uri,
            "scope": self._config.scope,
            "state": state,
            "prompt": "login",
            "max_age": "0",
        }
        url = f"{self._config.effective_auth_url}?" + urlencode(params)
        return LoginChallenge(type="redirect", redirect_url=url, state=state)

    async def exchange_code_fresh(self, code: str, state: str) -> FreshIdentity:
        # Wie exchange_code, aber zusätzlich auth_time aus dem ID-Token. Die State-
        # Signatur (an sub gebunden) prüft der Router via parse_stepup_state.
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                self._config.effective_token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._config.redirect_uri,
                    "client_id": self._config.client_id,
                    "client_secret": self._client_secret,
                },
            )
            token_resp.raise_for_status()
            token_json = token_resp.json()
            access_token = token_json["access_token"]

            userinfo_resp = await client.get(
                self._config.effective_userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            userinfo_resp.raise_for_status()

        identity = self._userinfo_to_identity(userinfo_resp.json())
        id_token = token_json.get("id_token")
        auth_time = None
        if id_token:
            claims = _unverified_jwt_claims(id_token)
            raw_at = claims.get("auth_time")
            if isinstance(raw_at, (int, float)):
                auth_time = int(raw_at)
        return FreshIdentity(identity=identity, auth_time=auth_time)

    def _verify_state(self, state: str) -> None:
        try:
            nonce, received_sig = state.rsplit(".", 1)
        except ValueError:
            raise ValueError("Ungültiges State-Format")
        expected_sig = hmac.new(
            self._school_secret.encode(), nonce.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, received_sig):
            raise ValueError("State-Signatur ungültig")

    def _userinfo_to_identity(self, userinfo: dict) -> NormalizedIdentity:
        external_id = userinfo["preferred_username"]
        # Claim-Key robust lesen: je nach Provider/Version `groups` oder `iserv:groups`.
        # Werte defensiv auf Strings normalisieren (manche Provider liefern Objekte).
        raw_groups = userinfo.get("groups") or userinfo.get("iserv:groups") or []
        raw_roles = userinfo.get("roles") or userinfo.get("iserv:roles") or []
        groups = _as_str_list(raw_groups)
        sso_roles = _as_str_list(raw_roles)
        roles, grade = self._map_roles_and_grade(groups, sso_roles)

        # Diagnose (immer, ohne PII): zeigt, ob `groups`/`roles` überhaupt ankommen.
        # Fehlt der Gruppen-Key komplett, ist meist der OAuth-Scope/-Clientrecht
        # in IServ das Problem, nicht das Matching.
        logger.info(
            "OAuth-Login: userinfo-Claims=%s, groups=%d, sso_roles=%s → Rollen=%s",
            sorted(userinfo.keys()),
            len(groups),
            sso_roles,
            roles,
        )
        if self._debug_userinfo:
            # Komplette userinfo (enthält PII!) — zeigt den exakten Key/die Struktur
            # der Gruppen. Nur temporär per AUTH_DEBUG_USERINFO=true aktivieren.
            logger.info("OAuth-Login [debug] vollständige userinfo=%r", userinfo)

        return NormalizedIdentity(
            external_id=external_id,
            roles=roles,
            grade=grade,
            display_name=userinfo.get("name", userinfo.get("preferred_username")),
            sso_groups=groups,
            sso_roles=sso_roles,
        )

    def _map_roles_and_grade(
        self, groups: list[str], sso_roles: list[str]
    ) -> tuple[list[str], str | None]:
        """Bildet SSO-Gruppen UND SSO-Rollen auf Plattform-Rollen ab.

        Gruppen und Rollen werden gemeinsam gegen ``group_role_map`` geprüft,
        damit z. B. die Gruppe ``Kollegium`` ODER die IServ-Rolle ``Lehrer`` zur
        Plattform-Rolle ``teacher`` führt. Das Matching ist **case-insensitiv**:
        IServ liefert Rollen kapitalisiert (``Lehrer``), Gruppennamen ggf.
        kleingeschrieben — die ``group_role_map`` darf beliebig geschrieben sein.
        """
        # Case-insensitiver Lookup über alle konfigurierten Namen
        lc_map = {name.lower(): role for name, role in self._group_role_map.items()}

        roles: set[str] = set()
        for name in (*groups, *sso_roles):
            mapped = lc_map.get(name.lower())
            if mapped is not None:
                roles.add(mapped)

        # Jahrgang nur aus Gruppen (case-insensitiv)
        grade: str | None = None
        if self._config.grade_group_pattern:
            pattern = re.compile(self._config.grade_group_pattern, re.IGNORECASE)
            for group in groups:
                m = pattern.match(group)
                if m:
                    grade = m.group(1)
                    break

        # Fallback: kein Rollen-Treffer → student. Der Adapter bleibt bewusst
        # provider-neutral (kein Login-Reject). Stille Downgrades diagnostiziert
        # man über die Roh-Gruppen/-Rollen im Profil.
        if not roles:
            roles.add("student")

        # grade nur bei Schüler:innen behalten (NormalizedIdentity-Invariante)
        if "student" not in roles:
            grade = None

        return list(roles), grade

