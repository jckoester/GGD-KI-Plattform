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
| `PEDAGOGY_PATH` | Pfad zur pedagogy.yaml | `config/pedagogy.yaml` |
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
  # OAuth-Scopes. IServ liefert die Gruppen-/Rollen-Claims NUR mit den Scopes
  # `iserv:groups`/`iserv:roles` (Achtung: `iserv:`-Präfix — `groups`/`roles` ohne
  # Präfix => „scope not allowed"). Der OAuth-Client muss in IServ dafür
  # freigeschaltet sein (IServ → Verwaltung → OAuth-Clients → Scopes).
  scope: "openid profile email iserv:groups iserv:roles"
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

# SSO-Gruppen UND SSO-Rollen → Plattform-Rollen.
# Jeder `group:`-Eintrag wird CASE-INSENSITIV sowohl gegen die Gruppen
# (`iserv:groups`) als auch gegen die Rollen (`iserv:roles`) der userinfo geprüft.
# WICHTIG: IServ liefert die Rollen als Symfony-Tokens ROLE_TEACHER, ROLE_STUDENT,
# ROLE_ADMIN (nicht "Lehrer"/"Schüler").
group_role_map:
  - group: ROLE_TEACHER    # IServ-Rollentoken
    role: teacher
  - group: Kollegium       # zusätzlich: schul-spezifische Lehrkraft-Gruppe
    role: teacher
  - group: ROLE_STUDENT    # IServ-Rollentoken
    role: student
  # Plattform-Admin bewusst über eine eigene, kleine Gruppe — NICHT über
  # ROLE_ADMIN (sonst wären alle IServ-Admins automatisch Plattform-Admins).
  - group: ki-admins
    role: admin

# SSO-Gruppenimport: Namensmuster für automatischen Gruppentyp-Zuordnung.
# Jedes Muster muss genau eine Capture-Group enthalten.
sso:
  # false = Lehrkräfte können keine Unterrichtsgruppen manuell anlegen;
  # sinnvoll, wenn der SSO-Provider alle Unterrichtsgruppen vollständig liefert.
  allow_manual_teaching_groups: true

  # Regex-Muster für Gruppentypen (je eine Capture-Group):
  groups:
    subject_department: '^FS\.(.+)$'        # FS.Mathematik → Fachschaft
    school_class: '^Klasse\.(.+)$'          # Klasse.8a → Schulklasse
    teaching_group: '^unterricht\.(.+)$'    # unterricht.8a.Mathematik → Unterrichtsgruppe
```

> **Fach-Aliase** (alternative SSO-Gruppennamen pro Fach, z. B. `fs.bildende.kunst`
> → Kunst) werden **nicht** hier, sondern pro Fach in `config/subjects.yaml`
> (Feld `sso_aliases`) gepflegt.

**Rollen:** `admin`, `teacher`, `student`, `review`. Das Matching ist
case-insensitiv und berücksichtigt Gruppen **und** Rollen, sodass z. B. die
Gruppe `Kollegium` oder das IServ-Rollentoken `ROLE_TEACHER` zu `teacher` führt.
Greift kein Eintrag, wird die Rolle auf **`student`** zurückgesetzt (kein
Login-Reject) — der Adapter bleibt damit provider-neutral.

> **Diagnose bei falscher Rolle:** Wird eine Lehrkraft fälschlich als Schüler:in
> eingestuft, fehlt meist nur ein passender `group_role_map`-Eintrag. Die
> betroffene Person findet die rohen, vom SSO gelieferten Gruppen und Rollen im
> eigenen **Profil → „SSO-Mitgliedschaften (Diagnose)"** — diese Namen exakt (in
> beliebiger Schreibweise) in `group_role_map` aufnehmen.
>
> **Diagnose „keine SSO-Daten" / alle sind student:** Zeigt das Profil *gar keine*
> Gruppen/Rollen und werden alle als `student` eingestuft, kommen die Claims nicht
> an. Prüfen:
> 1. `scope` enthält `iserv:groups` (mit Präfix!) **und** der OAuth-Client ist in
>    IServ für diesen Scope freigeschaltet (IServ → Verwaltung → OAuth-Clients).
>    Falscher Scope-Name → Redirect zurück mit `?error=...&error_description=…+scope+not+allowed`.
> 2. Server-Log beim Login: Die Zeile `OAuth-Login: userinfo-Claims=[…], groups=N`
>    zeigt, ob `groups`/`roles` überhaupt im Token sind. Fehlt der `groups`-Key,
>    ist es der Scope/das Clientrecht. Für die rohen Gruppenwerte im Log temporär
>    `AUTH_DEBUG_USERINFO=true` setzen.
> 3. Nach einer Scope-Änderung müssen sich Nutzer:innen **neu anmelden** (die
>    Gruppen stecken im 30-Tage-Cookie).

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

## `config/pedagogy.yaml`

Steuert die **pädagogischen Leitplanken** im System-Prompt (zielgruppendifferenziert):

- `preambles.universal_base` — gilt für **alle** Assistenten (Faktentreue,
  Prompt-Injection-Abwehr, Krisen-Hinweispflicht).
- `preambles.student_extension` / `teacher_extension` — Zielgruppen-Erweiterung; das
  Backend wählt nach `assistant.audience` (bzw. bei `audience: all` und ohne Assistent
  nach der Rolle der anfragenden Person).
- `student_augmentations` — sanfte Lernverhalten-Leitplanken (keine Komplettlösungen,
  sokratische Rückfragen …), **nur** für die Schüler-Behandlung. Pro Assistent über die
  Checkbox-Liste im Editor abschaltbar.
- `output_format` — universelle Ausgabe-Anweisung (Markdown ohne umschließende Fences).

Anders als die Krisen-Dateien ist `pedagogy.yaml` **versioniert**: Änderungen wirken erst
nach **Backend-Neustart** (Deployment-Gate + Git-Audit-Trail; kein Hot-Reload). Pfad-
Override über `PEDAGOGY_PATH`. Aufbau und Auswahl-Logik stehen in
[Content-Moderation & Guardrails](content-moderation.md), Abschnitt F.

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

Die **Jugendschutz-Guardrails** am Proxy (Block harter Ausgaben für alle Rollen) sowie
die zugehörigen Pattern-Dateien (`infra/guardrails/`) sind als kuratierungsbedürftige
Vorlage in `infra/litellm_config.example.yaml` enthalten — Details und die wichtige
Warnung zu Selbstverletzungs-Mustern stehen in
[Content-Moderation & Guardrails](content-moderation.md), Abschnitt B.

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
