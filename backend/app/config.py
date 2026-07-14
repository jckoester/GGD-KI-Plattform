from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Bekannte Platzhalter-/Beispiel-Keys, die in Produktion abgelehnt werden (Audit #9).
_PLACEHOLDER_MASTER_KEYS = {
    "sk-1234", "sk-1234567890", "changeme", "sk-changeme", "your-master-key", "sk-your-key",
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


settings = Settings()
