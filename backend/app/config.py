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


# Regel für Modell-Defaults in dieser Datei (IONOS-Plan, Schritt 8):
#
# * `chat_default_model` / `title_model` sind **leer**. Beide Variablen sind in jeder
#   Installation gesetzt; ein Anbietername als Code-Default wäre ein verstecktes
#   Routing-Ziel, das niemand konfiguriert hat und das der Proxy womöglich gar nicht kennt.
#   Fehlt `CHAT_DEFAULT_MODEL`, meldet das der Startup-Check in `app/main.py`.
# * `embedding_model` und `image_default_model` behalten dagegen einen konkreten Default —
#   beide Variablen sind neu, ihr Default IST also das bisherige Verhalten. Ein leerer Wert
#   würde bestehende Installationen brechen, die die Variable noch nicht kennen. Sie zu
#   neutralisieren lohnt erst, wenn alle Installationen sie explizit setzen.
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
    # ── Embedding-Modell (Kontextspeicher) ────────────────────────────────────
    # Der Name, unter dem der LiteLLM-Proxy das Embedding-Modell führt. Die Defaults
    # entsprechen bewusst dem BISHERIGEN Stand (OpenAI text-embedding-3-small, 1536
    # Dimensionen), damit bestehende Installationen ohne .env-Änderung weiterlaufen.
    # Der Wechsel auf ein anderes Modell (z. B. BGE-M3 mit 1024 Dimensionen) läuft über
    # .env + Migration + vollständiges Re-Embedding — siehe docs/runbooks/modellwechsel.md.
    embedding_model: str = "text-embedding-3-small"
    # Vektorbreite. MUSS zur Spalte `context_nodes.embedding` passen; ein Wechsel
    # erfordert eine Migration und ein Re-Embedding aller Knoten (alte Vektoren eines
    # anderen Modells sind semantisch wertlos, nicht nur formal inkompatibel).
    embedding_dimensions: int = 1536
    # Zeichen-Cap vor dem Embedding-Call (Token-Limit des Modells; konservativ, da
    # Zeichen ≠ Token). text-embedding-3-small und BGE-M3 liegen beide bei ~8k Tokens.
    embedding_max_chars: int = 16000
    # `dimensions`-Parameter mitsenden. Nur für Modelle, die das Kürzen der Vektorbreite
    # unterstützen (OpenAI text-embedding-3-*). BGE-M3 lehnt den Parameter ab.
    embedding_send_dimensions: bool = False
    # Wie viele Texte pro Embedding-Anfrage. Betrifft nur den Stapelbetrieb (Backfill,
    # Import) — ein einzeln angelegter Knoten geht weiterhin allein raus.
    # Der Hebel ist groß: Ein Aufruf je Knoten macht aus dem Re-Embedding des
    # Bildungsplans (~14.000 Knoten) einen mehrstündigen Lauf, im Stapel sind es Minuten.
    # Nach oben begrenzen ihn die Anfragegröße (batch × EMBEDDING_MAX_CHARS) und das
    # Zeitbudget des Anbieters, nicht die Vektorbreite.
    # 64 gemessen gegen BGE-M3 bei IONOS (28.08.2026): 1 → 0,8 Knoten/s · 8 → 11,5 ·
    # 32 → 22,4 · 64 → 32,7 · 128 → 35,0. Ab 64 ist der Zugewinn klein, während eine
    # fehlgeschlagene Anfrage immer mehr Knoten mitreißt.
    embedding_batch_size: int = 64
    # Obergrenze für den Tokendurchsatz im Stapelbetrieb; **0 = keine Drosselung**.
    # Getaktet wird nach dem tatsächlich abgerechneten Verbrauch (`usage.total_tokens`),
    # nicht nach einer Schätzung.
    #
    # Warum konfigurierbar und nicht einfach aus: Das passende Tempo hängt am Anbieter und
    # am Tarif. 3000/s ≈ 180.000 Tokens/Minute ist ein vorsichtiger Wert, der auch auf
    # kleinen Kontingenten trägt; wer Luft hat, setzt ihn hoch oder auf 0. Ohne Drosselung
    # laufen wir bei Stapel 64 auf grob 300.000 Tokens/Minute.
    #
    # Sich allein auf die 429-Wiederholung zu verlassen genügt nicht: Sie greift dreimal
    # und höchstens `EMBEDDING_RETRY_MAX_WAIT_S` lang. Bei anhaltender Drosselung ist das
    # Budget erschöpft, die Knoten bekommen Fehlermarken, und nach drei gescheiterten
    # Stapeln bricht der Lauf ab — aus „langsam, aber vollständig" würde „schnell abgebrochen".
    embedding_tokens_per_second: float = 3000.0
    # Wiederholversuche bei 429/503 (Rate-Limit bzw. vorübergehend nicht verfügbar).
    # Ein Rate-Limit ist ausdrücklich ein *vorübergehender* Zustand — ohne Wiederholung
    # bekommt der Knoten einen dauerhaften `embedding_error` und bleibt bis zum nächsten
    # Backfill-Lauf ohne Vektor. Betrifft vor allem den Massenfall: Nach einem
    # Bildungsplan-Import stehen Tausende Knoten ohne Embedding an.
    # 0 = nicht wiederholen. Die Wartezeit folgt `Retry-After`, sonst exponentiell.
    embedding_max_retries: int = 3
    # Obergrenze je Wartezeit. Begrenzt, wie lange ein Knoten-Anlegen im Request hängt
    # (enqueue_embedding_job läuft inline), auch wenn der Anbieter ein großes
    # `Retry-After` schickt.
    embedding_retry_max_wait_s: float = 5.0
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
    # ── Stundenplan-Quelle (UP-8) ─────────────────────────────────────────────
    # Ein schulweites Dienstkonto, einmal gesetzt, selten geändert — also dieselbe
    # Behandlung wie die übrigen Geheimnisse der Plattform. Bewusst KEINE Tabelle mit
    # verschlüsselter Konfiguration: Die stammte aus dem verworfenen Entwurf, in dem
    # jede Lehrkraft eine eigene Abo-URL gehabt hätte (75 Geheimnisse statt einem).
    #
    # `webuntis_server` leer = keine Stundenplan-Integration. Dann verschwinden die
    # zugehörigen Bedienelemente, statt Fehler zu melden (Plan §0) — eine Schule ohne
    # WebUntis soll davon nichts merken.
    webuntis_server: str = ""
    webuntis_user: str = ""
    webuntis_password: str = ""
    # NUR bei geteiltem Server nötig. Bei eigener Subdomain (z. B. ggd.webuntis.com) leer
    # lassen — sonst antwortet WebUntis mit `invalid schoolname` (-8500).
    webuntis_school: str = ""
    # ── Chat-Modelle ──────────────────────────────────────────────────────────
    # Beides sind die Namen, unter denen der LiteLLM-Proxy die Modelle führt — nicht die
    # IDs der Anbieter. Bewusst OHNE Code-Default: Ein hier hinterlegter Anbietername wäre
    # ein verstecktes Routing-Ziel, das niemand konfiguriert hat und das der Proxy womöglich
    # gar nicht kennt (dann: unverständlicher 400er). Fehlt der Wert, meldet das der
    # Startup-Check in app/main.py.
    chat_default_model: str = ""
    # Leer = keine automatische Titelgenerierung (der Chat-Flow prüft darauf).
    title_model: str = ""
    # Präfixe, deren Modelle NICHT im Chat-Modellwähler erscheinen: interne Modelle
    # (Titelgenerierung, Moderations-Klassifikator) und andere Modalitäten. Rein kosmetisch —
    # die Team-Allowlist bleibt unberührt, `system-titel` muss dort sogar stehen bleiben
    # (der Titel-Aufruf läuft über den Virtual Key der Nutzer:innen).
    #
    # Über Präfixe statt `model_info.mode`, weil Titel- und Moderationsmodell technisch
    # ebenfalls `mode: chat` sind. Konfigurierbar, weil die Namen eine Konvention des Admins
    # sind — wer anders benennt, passt die Liste an, statt dass der Filter stumm ins Leere greift.
    model_picker_hidden_prefixes: list[str] = ["system-", "embedding-", "bild-"]
    exchange_rate_fallback: float = 1.10
    # In welcher Währung die Preise in der LiteLLM-Config stehen (`input_cost_per_token`
    # & Co.) — NICHT, worin der Anbieter Rechnungen stellt.
    #
    # LiteLLM ist die Währung gleichgültig; „USD" ist nur ein Etikett auf einer Zahl.
    # Steht hier `EUR`, sind die eingetragenen Preise bereits Euro und es wird **nicht**
    # umgerechnet (Kurs 1,0). Das ist der Regelfall für Anbieter, die in Euro abrechnen —
    # IONOS listet ausschließlich Euro-Preise.
    #
    # Warum das mehr ist als Bequemlichkeit: Wer Euro-Preise zum Tageskurs in Dollar
    # umrechnet und einträgt, friert diesen Kurs ein. Das Budget wird aber mit dem
    # *aktuellen* EZB-Kurs umgerechnet — beide kürzen sich nur, solange die Kurse gleich
    # sind. Wertet der Euro auf, überschreitet die Schule ihr Budget genau um diesen
    # Faktor, jeden Monat, ohne dass etwas auffällt.
    #
    # `USD` bleibt der Vorgabewert: Anbieter wie OpenAI, Anthropic und Mistral rechnen in
    # Dollar, und LiteLLMs eingebaute Preistabelle ist durchgängig USD.
    litellm_price_currency: str = "USD"
    student_grades: list[int] = Field(default=[5, 6, 7, 8, 9, 10, 11, 12], alias="public_student_grades")
    # Host-Header-Allowlist für TrustedHostMiddleware (Audit #18). Default `*` (aus, wie bisher);
    # in Produktion die echten Hostnamen setzen, z. B. ["ki.example.de"]. Defense-in-Depth
    # zusätzlich zum Reverse-Proxy.
    allowed_hosts: list[str] = ["*"]
    # Vertrauenswürdige Reverse-Proxy-Adressen für die Audit-IP-Ableitung (Audit #13). Nur wenn
    # der direkte TCP-Peer hier gelistet ist, wird `X-Forwarded-For` ausgewertet — sonst spoofbar.
    trusted_proxies: list[str] = ["127.0.0.1", "::1"]
    # Wie viele Wissensknoten die Suche eines Assistenten zurückgibt. Getrennt von der
    # Anzeigezahl im Vorschlagsfenster (Profil, Vorgabe 8): Dort ging es um Platz, hier um
    # Kosten und Trefferabdeckung. Im Prüfsatz steht der erwartete Knoten in einem Fall
    # auf Rang 9 — mit 8 Plätzen wäre er unsichtbar. Jeder Treffer wiegt grob 75–100
    # Token, 20 also rund 2.000.
    assistant_context_limit: int = 20
    upload_max_bytes: int = 10 * 1024 * 1024  # 10 MB
    upload_max_files: int = 3
    assistant_schema_path: str = "config/assistant_schema.json"
    teacher_schoolwide_sharing_requires_admin: bool = True
    schulart: str = "GYM"
    export_school_name: str = ""  # Schulname für Curriculum-Export (PDF-Kopfzeile + YAML `schule`)
    # Name der Plattform, wie ihn auch das Frontend anzeigt (`branding.name`). Wird in der
    # Herkunftszeile exportierter Dokumente als **Werkzeug** genannt — das ist die Angabe,
    # die eine Quellenangabe braucht. Leer = die Zeile nennt nur Modell und Datum.
    public_school_name: str = ""
    # ── Bildgenerierung (Phase 16) ────────────────────────────────────────────
    # Default-Bildmodell (Name laut LiteLLM-Config) und großzügigeres Timeout, da die
    # Generierung Sekunden dauert und (anders als Chat) nicht gestreamt wird.
    image_default_model: str = "gpt-image-1"
    image_generation_timeout: float = 120.0
    # `response_format` für /images/generations. `b64_json` erzwingt Base64 — nötig für
    # Modelle, die sonst eine (extern gehostete) URL liefern würden; die verarbeitet der
    # Client bewusst nicht (Datenschutzgrenze). **Leer** = Parameter weglassen, für Modelle,
    # die ihn ablehnen und ohnehin nur Base64 liefern (gpt-image-1).
    #
    # Default leer, weil das dem bisherigen (hartcodierten) Verhalten entspricht: gpt-image-1
    # würde den Parameter mit 400 quittieren. Für FLUX/SDXL auf `b64_json` setzen.
    image_response_format: str = ""
    # Benannte Bildformate: Name → Pixelgröße. Der Name ist das, was das Modell im
    # `generate_image`-Tool wählt; die Pixelgröße geht an den Provider. Ein Anbieterwechsel
    # ändert damit nur die rechte Seite — die Schnittstelle zum Modell bleibt gleich.
    #
    # ⚠️ Nur Größen eintragen, für die in der LiteLLM-Config ein Preis hinterlegt ist:
    # sonst bleibt der Spend bei 0 und Budgets/Statistik greifen nicht. Die Defaults sind
    # gpt-image-1-Größen; SDXL/FLUX kennen andere (z. B. 1152x896, 1344x768).
    image_sizes: dict[str, str] = {
        "quadratisch": "1024x1024",
        "hoch": "1024x1536",
        "quer": "1536x1024",
    }
    # Format, das gilt, wenn das Modell keines oder ein unbekanntes angibt.
    image_default_format: str = "quadratisch"
    # Bildarten (Modell + Formate je Einsatzzweck). Fehlt die Datei, wird aus den vier
    # `image_*`-Werten oben genau eine Bildart `standard` synthetisiert — das Verhalten
    # bleibt dann exakt wie vor der Einführung. Damit sind jene vier Werte abgelöst.
    image_models_path: str = "config/image_models.yaml"
    image_blocklist_path: str = "config/image_blocklist.yaml"
    # Zustandsbericht des Jugendschutz-Klassifikators. Geschrieben wird er vom Guardrail
    # IM LITELLM-PROXY (`health_file` in dessen Config), gelesen von
    # `/admin/guardrail/health`. Beide müssen auf dieselbe Datei zeigen — in Docker also
    # auf einen gemeinsam gemounteten Pfad. Fehlt sie, meldet der Endpunkt „kein Bericht",
    # nicht „alles in Ordnung".
    guardrail_health_file: str = "data/guardrail_health.json"
    # Ab diesem Alter gilt der Bericht als veraltet und NICHT mehr als gesund. Schützt
    # gegen den gefährlichsten Zustand: Ein gestoppter Proxy (oder eine weggebrochene
    # gemeinsame Ablage) hinterlässt eine Datei mit `healthy: true`, die sonst unbegrenzt
    # Entwarnung gäbe. 24 h ist großzügig — der Proxy schreibt bei jeder geprüften Antwort.
    guardrail_health_max_age_h: float = 24.0
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

    @model_validator(mode="after")
    def _require_consistent_image_formats(self) -> "Settings":
        """`IMAGE_DEFAULT_FORMAT` muss ein Schlüssel aus `IMAGE_SIZES` sein.

        Bewusst ein harter Fehler statt einer stillen Korrektur: Eine falsche Größe wird
        beim Provider unter Umständen erzeugt, aber nicht abgerechnet (Spend = 0) — das
        fällt sonst erst auf, wenn die Budget-Statistik nicht mehr stimmt. Die Prüfung
        kostet nichts und die Fehlermeldung nennt die gültigen Werte.
        """
        if not self.image_sizes:
            raise ValueError(
                "IMAGE_SIZES ist leer. Mindestens ein Format als Name→Pixelgröße angeben, "
                'z. B. {"quadratisch": "1024x1024"}.'
            )
        if self.image_default_format not in self.image_sizes:
            raise ValueError(
                f"IMAGE_DEFAULT_FORMAT='{self.image_default_format}' ist kein Schlüssel aus "
                f"IMAGE_SIZES. Gültig: {', '.join(sorted(self.image_sizes))}."
            )
        return self

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
