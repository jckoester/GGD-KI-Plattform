import hashlib
import hmac
import re
import secrets
from typing import Literal
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, model_validator

from app.auth.base import AuthAdapter, LoginChallenge, NormalizedIdentity
from app.config import Settings


class IServConfig(BaseModel):
    base_url: str  # z.B. https://iserv.example.de
    client_id: str
    redirect_uri: str
    grade_group_pattern: str | None = None
    # Regex mit genau einer Capture-Group, die den Jahrgangswert liefert.
    # Beispiel GGD: "^jahrgang\.(\d{1,2})$"
    # None → Jahrgangs-Erkennung deaktiviert, grade ist immer None
    # client_secret kommt aus Settings (Env-Variable), nicht aus YAML

    @model_validator(mode="after")
    def check_grade_pattern_has_capture_group(self) -> "IServConfig":
        if self.grade_group_pattern is not None:
            try:
                compiled = re.compile(self.grade_group_pattern)
            except re.error as e:
                raise ValueError(
                    f"grade_group_pattern ist kein gültiges Regex: {e}"
                )
            if compiled.groups < 1:
                raise ValueError(
                    "grade_group_pattern muss genau eine Capture-Group enthalten"
                )
        return self


class IServAdapter(AuthAdapter):
    def __init__(
        self,
        raw: dict,
        settings: Settings,
        group_role_map: dict[str, str] | None = None,
    ) -> None:
        self._config = IServConfig.model_validate(raw)
        self._client_secret = settings.auth_iserv_client_secret
        self._school_secret = settings.school_secret
        self._group_role_map = group_role_map or {}

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
            "scope": "openid profile email",
            "state": state,
        }
        url = (
            f"{self._config.base_url}/iserv/oauth/v2/auth?"
            + urlencode(params)
        )
        return LoginChallenge(type="redirect", redirect_url=url, state=state)

    async def exchange_code(self, code: str, state: str) -> NormalizedIdentity:
        self._verify_state(state)
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                f"{self._config.base_url}/iserv/oauth/v2/token",
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
                f"{self._config.base_url}/iserv/oauth/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            userinfo_resp.raise_for_status()

        return self._userinfo_to_identity(userinfo_resp.json())

    async def authenticate_direct(
        self, username: str, password: str
    ) -> NormalizedIdentity | None:
        raise NotImplementedError("IServAdapter unterstützt kein direktes Login")

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
        groups: list[str] = userinfo.get("groups", [])
        role = self._map_role(groups)
        grade = self._extract_grade(groups) if role == "student" else None
        return NormalizedIdentity(external_id=external_id, role=role, grade=grade)

    def _map_role(
        self, groups: list[str]
    ) -> Literal["student", "teacher", "admin"]:
        # Gruppen gegen group_role_map prüfen, Priorität: admin > teacher > student
        # Kein Match → "student" als sicherer Default
        role_priority: list[Literal["admin", "teacher", "student"]] = [
            "admin",
            "teacher",
            "student",
        ]
        for priority_role in role_priority:
            for group, role in self._group_role_map.items():
                if role == priority_role and group in groups:
                    return priority_role
        return "student"

    def _extract_grade(self, groups: list[str]) -> str | None:
        if self._config.grade_group_pattern is None:
            return None
        pattern = re.compile(self._config.grade_group_pattern)
        for group in groups:
            m = pattern.match(group)
            if m:
                return m.group(1)
        return None
