import yaml
from dataclasses import dataclass
from typing import Literal

from passlib.hash import bcrypt
from pydantic import BaseModel

from app.auth.base import AuthAdapter, LoginChallenge, NormalizedIdentity


class YamlTestConfig(BaseModel):
    users_file: str  # Pfad zur YAML-Datei mit Testnutzern


@dataclass
class YamlUser:
    username: str
    password_hash: str  # bcrypt-Hash
    role: Literal["student", "teacher", "admin"]
    grade: str | None  # nur bei role="student"


class YamlTestAdapter(AuthAdapter):
    def __init__(self, raw: dict, group_role_map: dict[str, str] | None = None) -> None:
        self._config = YamlTestConfig.model_validate(raw)
        self._group_role_map = group_role_map or {}
        self._users: dict[str, YamlUser] = self._load_users()

    def _load_users(self) -> dict[str, YamlUser]:
        """Lädt die Testnutzer aus der YAML-Datei."""
        with open(self._config.users_file) as f:
            data = yaml.safe_load(f)
        users: dict[str, YamlUser] = {}
        for user_data in data.get("users", []):
            user = YamlUser(
                username=user_data["username"],
                password_hash=user_data["password_hash"],
                role=user_data["role"],
                grade=user_data.get("grade"),
            )
            users[user.username] = user
        return users

    @property
    def mode(self) -> Literal["direct"]:
        return "direct"

    async def get_login_challenge(self) -> LoginChallenge:
        return LoginChallenge(type="form")

    async def exchange_code(self, code: str, state: str) -> NormalizedIdentity:
        raise NotImplementedError("YamlTestAdapter unterstützt kein OIDC")

    async def authenticate_direct(
        self, username: str, password: str
    ) -> NormalizedIdentity | None:
        user = self._users.get(username)
        if user is None:
            return None
        if not bcrypt.verify(password, user.password_hash):
            return None
        return NormalizedIdentity(
            external_id=username,
            role=user.role,
            grade=user.grade,
        )
