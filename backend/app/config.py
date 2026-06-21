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
    frontend_origin: str = "http://localhost:5173"
    environment: str = "development"
    auth_config_path: str = "config/auth.yaml"
    budget_tiers_path: str = "config/budget_tiers.yaml"
    crisis_triggers_path: str = "config/crisis_triggers.yaml"
    help_resources_path: str = "config/help_resources.yaml"
    auth_iserv_client_secret: str = ""
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
    curriculum_extract_model: str = ""
    curriculum_extract_max_pages_per_call: int = 4
    curriculum_extract_concurrency: int = 3


settings = Settings()
