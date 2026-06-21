from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

BASE_ROLES = {"student", "teacher", "admin"}

# Rollen, die für sich allein einen gültigen Login bilden. `review`
# (Schulsozialarbeit/Krisen-Einsicht) ist kein Chat-Identitätstyp wie die
# Basisrollen, darf aber eigenständig vorkommen — eine Review-Person ist nicht
# zwingend Lehrkraft. Budget-/LiteLLM-seitig fällt sie über get_primary_role
# auf die Teacher-Behandlung zurück.
LOGIN_ROLES = BASE_ROLES | {"review"}


class NormalizedIdentity(BaseModel):
    external_id: str
    roles: list[str]  # mind. eine eigenständige Login-Rolle; admin additiv zu teacher
    grade: str | None = None
    display_name: str | None = None  # nur UI-Anzeige, niemals persistieren
    sso_groups: list[str] = []  # rohe SSO-Gruppen-IDs vom Provider

    @model_validator(mode="after")
    def validate_roles(self) -> "NormalizedIdentity":
        if not any(r in LOGIN_ROLES for r in self.roles):
            raise ValueError(
                "roles muss mind. eine eigenständige Login-Rolle enthalten "
                "(student/teacher/admin/review)"
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
