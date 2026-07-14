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
    sso_roles: list[str] = []  # rohe SSO-Rollen (z.B. IServ: Lehrer/Schüler/Administrator)

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
    # PKCE-`code_verifier` (Audit #4): router-intern. Der Router legt ihn in ein
    # kurzlebiges HttpOnly-Cookie (Browser-Bindung + PKCE) und gibt ihn **nie** an den
    # Client zurück (wird vor der Antwort auf None gesetzt).
    code_verifier: str | None = None


@dataclass
class FreshIdentity:
    """Ergebnis einer Step-up-Re-Authentifizierung (Redirect-Pfad).

    `auth_time` ist der Unix-Zeitpunkt der IdP-Authentifizierung aus dem ID-Token
    (None, wenn der Provider keinen liefert) — Grundlage der Frische-Prüfung.
    """

    identity: NormalizedIdentity
    auth_time: int | None


class AuthAdapter(ABC):
    @property
    @abstractmethod
    def mode(self) -> Literal["redirect", "direct"]: ...

    @abstractmethod
    async def get_login_challenge(self) -> LoginChallenge: ...

    @abstractmethod
    async def exchange_code(
        self, code: str, state: str, code_verifier: str | None = None
    ) -> NormalizedIdentity: ...

    @abstractmethod
    async def authenticate_direct(
        self, username: str, password: str
    ) -> NormalizedIdentity | None: ...

    # ---- Step-up-Re-Authentifizierung (Phase 12, Schritt 5) ----
    # Nur der Redirect-Pfad braucht diese Methoden; der direct-Adapter nutzt für
    # Step-up authenticate_direct() und überschreibt sie daher nicht.

    async def get_stepup_challenge(self, state: str) -> LoginChallenge:
        raise NotImplementedError(
            "Dieser Adapter unterstützt keine Redirect-Step-up-Challenge"
        )

    async def exchange_code_fresh(self, code: str, state: str) -> FreshIdentity:
        raise NotImplementedError(
            "Dieser Adapter unterstützt keinen Redirect-Step-up-Austausch"
        )
