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
    # Bildgenerierung (Phase 16) — Default-Bildmodell, Standardgröße (nur abgerechnete
    # Größen verwenden, sonst Spend=0-Risiko) und großzügigeres Timeout, da die
    # Generierung Sekunden dauert und (anders als Chat) nicht gestreamt wird.
    image_default_model: str = "gpt-image-1"
    image_default_size: str = "1024x1024"
    image_generation_timeout: float = 120.0
    image_blocklist_path: str = "config/image_blocklist.yaml"
    # Ablage generierter Bilder (repo-root-relativ, falls nicht absolut) + harte
    # Maximal-Aufbewahrung als Backstop. Normalerweise stirbt ein Bild mit seiner
    # Konversation (93-Tage-Lifecycle); der Max-Wert (>> 93+180) fängt Anomalien ab.
    image_storage_dir: str = "data/generated_images"
    image_max_retention_days: int = 400

    # ── Server-Rendering (Phase 17) ──────────────────────────────────────────
    # Interner Node-Render-Sidecar (CircuiTikZ→SVG, KaTeX). Nur lokal/compose-intern
    # erreichbar; nie öffentlich. render_timeout etwas höher als der sidecar-eigene
    # Render-Timeout, damit ein legitimer, langsamer Render nicht clientseitig abbricht.
    render_sidecar_url: str = "http://127.0.0.1:3200"
    render_timeout: float = 15.0
    # Aufbewahrung des SVG-Caches (rendered_svg); altersbasierter Aufräum-Cron.
    render_cache_max_age_days: int = 90
    # Plot-Rendering (matplotlib, in-process): Timeout gegen pathologische Funktionen.
    plot_render_timeout: float = 10.0

    # ── Artefaktbibliothek (Phase 18) ────────────────────────────────────────
    # Ablage der Artefakt-Bytes (repo-root-relativ, falls nicht absolut).
    artifact_storage_dir: str = "data/artifacts"
    # Role-/jahrgangsbasierte Aufbewahrung + Quota (Struktur wie budget_tiers.yaml).
    artifact_limits_path: str = "config/artifact_limits.yaml"

    # ── Material-Werkstatt / Pandoc (Phase 19) ───────────────────────────────
    # Office-Export (DOCX/ODT) läuft über Pandoc als Subprozess. PDF nutzt weiterhin die
    # weasyprint-Pipeline (Phase 17). Fehlt das Binary, wird der Office-Export sauber
    # deaktiviert (Feature-Flag), statt zu crashen.
    pandoc_bin: str = "pandoc"
    pandoc_timeout: float = 20.0
    pandoc_max_input_chars: int = 500_000
    # Ablage schulweiter Export-Vorlagen (DOCX/ODT-reference-docs). CSS liegt in site_config.
    # In Docker absolut aufs ./data-Volume setzen (persistent), sonst repo-root-relativ.
    export_template_dir: str = "data/export_templates"
    export_reference_max_bytes: int = 5_242_880  # 5 MB


settings = Settings()
