from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../config/.env",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str
    school_secret: str
    jwt_secret: str
    litellm_proxy_url: str = "http://localhost:4000"
    litellm_master_key: str = ""
    frontend_origin: str = "http://localhost:5173"
    environment: str = "development"
    auth_config_path: str = "config/auth.yaml"
    budget_tiers_path: str = "config/budget_tiers.yaml"
    auth_iserv_client_secret: str = ""
    jwt_algorithm: str = "HS256"
    chat_default_model: str = "openai/gpt-4o-mini"


settings = Settings()
