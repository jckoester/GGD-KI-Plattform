from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

BASE_ROLES = {"student", "teacher", "admin"}


class NormalizedIdentity(BaseModel):
    external_id: str
    roles: list[str]  # mind. eine Basisrolle; admin additiv zu teacher möglich
    grade: str | None = None
    display_name: str | None = None  # nur UI-Anzeige, niemals persistieren
    sso_groups: list[str] = []  # rohe SSO-Gruppen-IDs vom Provider

    @model_validator(mode="after")
    def validate_roles(self) -> "NormalizedIdentity":
        if not any(r in BASE_ROLES for r in self.roles):
            raise ValueError(
                "roles muss mind. eine Basisrolle enthalten (student/teacher/admin)"
            )
        if self.grade is not None and "student" not in self.roles:
            raise ValueError("grade darf nur gesetzt sein, wenn 'student' in roles")
        return self


@dataclass
class LoginChallenge:
    type: Literal["redirect", "form"]
    redirect_url: str | None = None
    state: str | None = None


class AuthAdapter(ABC):
    @property
    @abstractmethod
    def mode(self) -> Literal["redirect", "direct"]: ...

    @abstractmethod
    async def get_login_challenge(self) -> LoginChallenge: ...

    @abstractmethod
    async def exchange_code(self, code: str, state: str) -> NormalizedIdentity: ...

    @abstractmethod
    async def authenticate_direct(
        self, username: str, password: str
    ) -> NormalizedIdentity | None: ...
