from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


class NormalizedIdentity(BaseModel):
    external_id: str
    role: Literal["student", "teacher", "admin"]
    grade: str | None = None

    @model_validator(mode="after")
    def grade_only_for_student(self) -> "NormalizedIdentity":
        if self.grade is not None and self.role != "student":
            raise ValueError(
                "Klasse (`grade`) darf nur bei `role='student'` gesetzt sein"
            )
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
