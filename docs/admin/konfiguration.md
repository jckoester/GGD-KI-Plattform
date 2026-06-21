# Konfigurationsdateien

Alle Konfigurationsdateien liegen im Verzeichnis `config/` (Laufzeitkonfiguration)
und `infra/` (Infrastruktur). Beispieldateien enden auf `.example.yaml` bzw.
`.example` und werden nicht in den Betrieb übernommen.

---

## `.env`

Umgebungsvariablen für Backend und Frontend. Wird von Docker Compose eingelesen.

| Variable | Beschreibung | Beispiel |
|----------|-------------|---------|
| `POSTGRES_PASSWORD` | Datenbankpasswort | `openssl rand -base64 32` |
| `DATABASE_URL` | Vollständige Datenbank-URL | `postgresql+asyncpg://postgres:<PW>@db:5432/ggd_ki` |
| `SCHOOL_SECRET` | HMAC-Schlüssel für Pseudonymisierung — **niemals nach Inbetriebnahme ändern** | `openssl rand -base64 32` |
| `JWT_SECRET` | Schlüssel für JWT-Session-Tokens | `openssl rand -base64 32` |
| `LITELLM_PROXY_URL` | Interne URL des LiteLLM-Containers | `http://litellm:4000` |
| `LITELLM_MASTER_KEY` | Zugangsschlüssel für LiteLLM-Admin-API | `sk-...` |
| `CHAT_DEFAULT_MODEL` | Vorausgewähltes Modell im Chat | `gpt-4o-mini` |
| `TITLE_MODEL` | Modell für automatische Gesprächstitel | `gpt-4o-mini` |
| `CURRICULUM_EXTRACT_MODEL` | Modell für die LLM-Extraktion beim Bildungsplan-Import (leer → `CHAT_DEFAULT_MODEL`). Siehe Abschnitt *Curriculum-Extraktion* | `gpt-4o` |
| `CURRICULUM_EXTRACT_MAX_PAGES_PER_CALL` | Seiten pro LLM-Aufruf (Chunk-Größe beim Import) | `4` |
| `CURRICULUM_EXTRACT_CONCURRENCY` | Parallele Extraktions-Aufrufe | `3` |
| `FRONTEND_ORIGIN` | Öffentliche URL der Plattform (für CORS) | `https://ki.beispielschule.de` |
| `ENVIRONMENT` | `development` oder `production` | `production` |
| `AUTH_CONFIG_PATH` | Pfad zur auth.yaml | `config/auth.yaml` |
| `BUDGET_TIERS_PATH` | Pfad zur budget_tiers.yaml | `config/budget_tiers.yaml` |
| `CRISIS_TRIGGERS_PATH` | Pfad zur crisis_triggers.yaml | `config/crisis_triggers.yaml` |
| `HELP_RESOURCES_PATH` | Pfad zur help_resources.yaml | `config/help_resources.yaml` |
| `AUTH_ISERV_CLIENT_SECRET` | OAuth2-Client-Secret des SSO-Providers | *(vom Provider) |
| `STUDENT_GRADES` | Jahrgangsstufen als JSON-Array | `[5,6,7,8,9,10,11,12]` |
| `PUBLIC_SCHOOL_NAME` | Anzeigename der Plattform | `ki@beispielschule` |
| `PUBLIC_SCHOOL_LOGO_URL` | Logo-URL (Fallback für beide Themes) | *(leer → Initialen)* |
| `PUBLIC_SCHOOL_LOGO_URL_LIGHT` | Logo für helles Theme | `/static/logo-light.png` |
| `PUBLIC_SCHOOL_LOGO_URL_DARK` | Logo für dunkles Theme | `/static/logo-dark.png` |

> **Wichtig:** `SCHOOL_SECRET` darf nach der ersten Inbetriebnahme nie geändert
> werden. Alle Pseudonyme würden sich dadurch ändern — bestehende Nutzerkonten
> und Gesprächsverläufe wären nicht mehr zuordenbar.

---

## `config/auth.yaml`

Steuert, welcher Authentifizierungsadapter verwendet wird, wie SSO-Gruppen
auf Plattform-Rollen abgebildet werden und wie Unterrichtsgruppen aus dem
SSO-Import befüllt werden.

```yaml
# Aktiver Adapter: "oauth" für Produktion, "yaml_test" für Entwicklung
adapter: oauth

oauth:
  base_url: https://sso.beispielschule.de
  client_id: ki-plattform
  redirect_uri: https://ki.beispielschule.de/auth/callback
  # Regex mit Capture-Group für den Jahrgang aus dem Gruppenname.
  # Beispiel: Gruppe "jahrgang.10" → grade="10"
  grade_group_pattern: '^jahrgang\.(\d{1,2})$'
  # Deaktivieren: auf null setzen oder auskommentieren
  # grade_group_pattern: null
  # Optionale Endpunkt-Overrides. Standard: IServ-Pfade unterhalb von base_url.
  # Nur setzen, wenn ein anderer OAuth2/OIDC-Provider verwendet wird:
  # auth_url: "https://sso.beispielschule.de/oauth2/authorize"
  # token_url: "https://sso.beispielschule.de/oauth2/token"
  # userinfo_url: "https://sso.beispielschule.de/oauth2/userinfo"

yaml_test:
  users_file: config/test_users.yaml

# SSO-Gruppen → Plattform-Rollen
group_role_map:
  - group: ki-admins
    role: admin
  - group: lehrer
    role: teacher
  - group: schueler
    role: student

# SSO-Gruppenimport: Namensmuster für automatischen Gruppentyp-Zuordnung.
# Jedes Muster muss genau eine Capture-Group enthalten.
sso:
  # false = Lehrkräfte können keine Unterrichtsgruppen manuell anlegen;
  # sinnvoll, wenn der SSO-Provider alle Unterrichtsgruppen vollständig liefert.
  allow_manual_teaching_groups: true

  # Kurzname → Subject-Slug (Groß-/Kleinschreibung wird ignoriert).
  # Nötig, wenn SSO-Gruppen Kürzel verwenden, die vom Fach-Slug abweichen.
  subject_aliases:
    D:    deutsch
    E:    englisch
    M:    mathematik
    Bio:  biologie
    Ch:   chemie
    Ph:   physik

  # Regex-Muster für Gruppentypen (je eine Capture-Group):
  groups:
    subject_department: '^FS\.(.+)$'        # FS.Mathematik → Fachschaft
    school_class: '^Klasse\.(.+)$'          # Klasse.8a → Schulklasse
    teaching_group: '^unterricht\.(.+)$'    # unterricht.8a.Mathematik → Unterrichtsgruppe
```

**Rollen:** `admin`, `teacher`, `student`. Nutzer:innen, deren SSO-Gruppen
keiner Rolle zugeordnet sind, können sich nicht einloggen.

> **Hinweis:** Das Client-Secret des SSO-Providers wird **nicht** in dieser Datei
> gespeichert, sondern über die Umgebungsvariable `AUTH_ISERV_CLIENT_SECRET` in
> `.env` übergeben.

---

## `config/budget_tiers.yaml`

Legt die monatlichen Euro-Budgets pro Jahrgansstufe und Rolle fest.

```yaml
grades:
  5:
    budget_duration: 1mo
    max_budget_eur: 1.00
  # … weitere Jahrgänge …
  12:
    budget_duration: 1mo
    max_budget_eur: 3.50

roles:
  teacher:
    budget_duration: 1mo
    max_budget_eur: 8.00
```

Änderungen an dieser Datei wirken erst beim nächsten Monats-Reconcile
(1. des Monats, 07:00 Uhr). Um Änderungen sofort anzuwenden:

```bash
docker compose exec backend python scripts/monthly_budget_reconcile.py
```

---

## `config/crisis_triggers.yaml` und `config/help_resources.yaml`

Steuern die Krisen-Erkennung: `crisis_triggers.yaml` enthält die Stichwort-/
Phrasenmuster je Kategorie, `help_resources.yaml` die Anlaufstellen, die im
Hilfe-Banner erscheinen. Beide werden beim Start eingelesen und zwischengespeichert —
nach Änderungen das **Backend neu starten** (im Dev-Betrieb löst `--reload` für
Dateien außerhalb `backend/` keinen Reload aus).

Aufbau, Beispiele und Pflegehinweise (Abstimmung mit der Schulsozialarbeit) stehen
in [Content-Moderation & Guardrails](content-moderation.md), Abschnitt D.

Die Pfade lassen sich über `CRISIS_TRIGGERS_PATH` / `HELP_RESOURCES_PATH` in `.env`
überschreiben (Standard: `config/crisis_triggers.yaml` bzw.
`config/help_resources.yaml`).

---

## `infra/litellm_config.yaml`

Konfiguriert den LiteLLM-Proxy: welche KI-Modelle verfügbar sind, über
welche Anbieter sie geroutet werden und mit welchem Master Key der Proxy
gesichert ist.

```yaml
model_list:
  - model_name: gpt-4o-mini
    litellm_params:
      model: openai/gpt-4o-mini
      api_key: sk-...

  - model_name: claude-sonnet
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: sk-ant-...

  - model_name: ollama/llama3
    litellm_params:
      model: ollama/llama3
      api_base: http://ollama:11434

general_settings:
  master_key: sk-...   # muss mit LITELLM_MASTER_KEY in .env übereinstimmen
```

Die vollständige Referenz für `model_list` und Anbieter-Konfigurationen
findet sich in der [LiteLLM-Dokumentation](https://docs.litellm.ai).

---

## Curriculum-Extraktion (Bildungsplan-Import)

Beim Import eines Bildungsplan-Dokuments (PDF/Word) über die Verwaltungsoberfläche
extrahiert ein LLM die Kapitelstruktur. Der Aufruf läuft ausschließlich über den
LiteLLM-Proxy und nutzt strukturierte Ausgabe (`response_format`). Gesteuert wird
das über die drei `CURRICULUM_EXTRACT_*`-Variablen in `.env` (siehe Tabelle oben).

> Der Wert von `CURRICULUM_EXTRACT_MODEL` muss **exakt** einem `model_name` aus
> `infra/litellm_config.yaml` entsprechen. Ein unbekannter Name führt beim Import
> zu einem 404 vom Proxy, ein Modell ohne `response_format`-Unterstützung zu einem
> 400 (jedes Kapitel erscheint dann als „Fehler bei Extraktion").

### Anforderung an das Modell

Das Modell muss `response_format` unterstützen — idealerweise striktes
`json_schema` (Structured Outputs). Der Import versucht gestuft:
`json_schema` (strict) → `json_object` → ganz ohne `response_format`. Ein Modell,
das die strikte Stufe beherrscht, liefert die zuverlässigsten Ergebnisse; die
weiteren Stufen sind nur ein Sicherheitsnetz und ohne Schema-Garantie.

### Geeignete Modelle

| Eignung | Modelle | Hinweis |
|---------|---------|---------|
| **Empfohlen** — strict `json_schema` | OpenAI `gpt-4o` (Snapshot 2024-08-06 oder neuer), `gpt-4o-mini`, `gpt-4.1`-Reihe, `o`-Reihe (Reasoning-Modelle), `gpt-5`-Reihe · Google Gemini 2.0+ · xAI Grok-2+ · Anthropic Claude Sonnet 4.5 / Opus 4.1 (über LiteLLM, Beta-Header wird automatisch gesetzt) | Beste Struktur-Treue; die primäre Stufe greift direkt |
| **Funktioniert über Fallback** — nur `json_object` | Ältere Claude-Modelle ohne Structured-Outputs-Beta, Gemini 1.5, diverse Bedrock-Modelle | Läuft, aber ohne Schema-Garantie; vereinzelt Nachpflege im Prüfschritt nötig |
| **Ungeeignet** | Legacy `gpt-4`, `gpt-4-turbo`, `gpt-3.5-turbo` (kein `response_format`) · kleine lokale Ollama-Modelle | `gpt-4` löst den 400-Fehler aus; lokale Klein-Modelle: Extraktionsqualität ungeprüft |

### Empfehlung für die Praxis

Der Import läuft selten (Erst- oder Re-Import eines Bildungsplans), daher ist ein
stärkeres, etwas teureres Modell vertretbar. Für die fragmentierten, mehrspaltigen
Tabellen mancher Fächer liefern `gpt-4o` und `Claude Sonnet 4.5` in der Praxis die
robustesten Ergebnisse; `gpt-4o-mini` ist günstiger und für sauber gesetzte
Curricula meist ausreichend. Die Extraktion sollte unabhängig vom Modell nach jedem
Import im Prüfschritt der Verwaltungsoberfläche kontrolliert werden.
