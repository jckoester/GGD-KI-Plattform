from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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


settings = Settings()
