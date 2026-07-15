from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Bekannte Platzhalter-/Beispiel-Keys, die in Produktion abgelehnt werden (Audit #9).
_PLACEHOLDER_MASTER_KEYS = {
    "sk-1234", "sk-1234567890", "changeme", "sk-changeme", "your-master-key", "sk-your-key",
}

# Mindestlänge für die Krypto-Geheimnisse in Produktion (Audit #7).
# `openssl rand -base64 32` erzeugt ~44 Zeichen — 32 ist die untere Schranke.
_MIN_SECRET_LEN = 32

# Bekannte Platzhalter-/Test-Werte für SCHOOL_SECRET/JWT_SECRET (Audit #7).
_PLACEHOLDER_SECRETS = {
    "changeme", "change-me", "secret", "your-secret", "your-school-secret", "your-jwt-secret",
    "test", "test-secret", "test-school-secret", "test-jwt-secret", "dev", "development",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str
    school_secret: str
    jwt_secret: str
    litellm_proxy_url: str = "http://localhost:4000"
    litellm_master_key: str = ""
    litellm_verify_ssl: bool = True
    # Inline-Embedding-Generierung beim Anlegen/Ändern von Knoten (enqueue_embedding_job).
    # In Tests deaktivierbar, da dort kein LiteLLM-Proxy läuft.
    embeddings_enabled: bool = True
    frontend_origin: str = "http://localhost:5173"
    environment: str = "development"
    auth_config_path: str = "config/auth.yaml"
    budget_tiers_path: str = "config/budget_tiers.yaml"
    crisis_triggers_path: str = "config/crisis_triggers.yaml"
    help_resources_path: str = "config/help_resources.yaml"
    pedagogy_path: str = "config/pedagogy.yaml"
    rate_limits_path: str = "config/rate_limits.yaml"
    auth_iserv_client_secret: str = ""
    # Wenn True, loggt der OAuth-Adapter beim Login die rohen userinfo-Gruppen/-Rollen
    # (zur Diagnose der Rollen-/Fächer-Zuordnung). Enthält Gruppennamen → nur temporär
    # aktivieren. Standard-Log (ohne Werte: Claim-Keys + Anzahl) läuft immer.
    auth_debug_userinfo: bool = False
    jwt_algorithm: str = "HS256"
    chat_default_model: str = "openai/gpt-4o-mini"
    title_model: str = ""
    exchange_rate_fallback: float = 1.10
    student_grades: list[int] = Field(default=[5, 6, 7, 8, 9, 10, 11, 12], alias="public_student_grades")
    # Host-Header-Allowlist für TrustedHostMiddleware (Audit #18). Default `*` (aus, wie bisher);
    # in Produktion die echten Hostnamen setzen, z. B. ["ki.example.de"]. Defense-in-Depth
    # zusätzlich zum Reverse-Proxy.
    allowed_hosts: list[str] = ["*"]
    # Vertrauenswürdige Reverse-Proxy-Adressen für die Audit-IP-Ableitung (Audit #13). Nur wenn
    # der direkte TCP-Peer hier gelistet ist, wird `X-Forwarded-For` ausgewertet — sonst spoofbar.
    trusted_proxies: list[str] = ["127.0.0.1", "::1"]
    spend_log_delay: float = 1.0
    upload_max_bytes: int = 10 * 1024 * 1024  # 10 MB
    upload_max_files: int = 3
    assistant_schema_path: str = "config/assistant_schema.json"
    teacher_schoolwide_sharing_requires_admin: bool = True
    schulart: str = "GYM"
    export_school_name: str = ""  # Schulname für Curriculum-Export (PDF-Kopfzeile + YAML `schule`)

    @model_validator(mode="after")
    def _require_strong_master_key_in_prod(self) -> "Settings":
        """In Produktion muss `LITELLM_MASTER_KEY` stark sein (Sicherheits-Audit #9).

        Der Master-Key gibt volle Kontrolle über den LiteLLM-Proxy (Key-Minting, Budgets) —
        ein leerer/Platzhalter-/zu kurzer Wert wäre bei Netz-Exposition fatal. In `development`
        bleibt der schwache Dev-Key (z. B. `sk-1234`) für den lokalen Proxy erlaubt.
        """
        if self.environment == "development":
            return self
        key = (self.litellm_master_key or "").strip()
        if len(key) < 20 or key.lower() in _PLACEHOLDER_MASTER_KEYS:
            raise ValueError(
                "LITELLM_MASTER_KEY fehlt, ist ein Platzhalter oder zu kurz. In Produktion einen "
                "starken, zufälligen Schlüssel (≥ 20 Zeichen) setzen — er gewährt volle Kontrolle "
                "über den LiteLLM-Proxy."
            )
        return self

    @model_validator(mode="after")
    def _require_strong_secrets_in_prod(self) -> "Settings":
        """In Produktion müssen `SCHOOL_SECRET` und `JWT_SECRET` stark sein (Sicherheits-Audit #7).

        `SCHOOL_SECRET` ist der HMAC-Schlüssel der Pseudonymisierung — ist er schwach/erratbar,
        lassen sich Pseudonyme rückführen (Bruch der Datenschutz-Invariante). `JWT_SECRET` signiert
        die Auth-Cookies — schwach bedeutet fälschbare Sitzungen. In `development` bleiben kurze
        Test-Werte erlaubt, damit die lokale Umgebung/Tests nicht brechen.
        """
        if self.environment == "development":
            return self
        for name, value in (("SCHOOL_SECRET", self.school_secret), ("JWT_SECRET", self.jwt_secret)):
            secret = (value or "").strip()
            if len(secret) < _MIN_SECRET_LEN or secret.lower() in _PLACEHOLDER_SECRETS:
                raise ValueError(
                    f"{name} fehlt, ist ein Platzhalter oder zu kurz. In Produktion einen starken, "
                    f"zufälligen Wert (≥ {_MIN_SECRET_LEN} Zeichen, z. B. `openssl rand -base64 32`) "
                    "setzen — schwache Krypto-Geheimnisse erlauben Pseudonym-Rückführung bzw. "
                    "Token-Fälschung."
                )
        return self


settings = Settings()
