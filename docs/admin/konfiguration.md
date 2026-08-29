# Konfigurationsdateien

Alle Konfigurationsdateien liegen im Verzeichnis `config/` (Laufzeitkonfiguration)
und `infra/` (Infrastruktur). Beispieldateien enden auf `.example.yaml` bzw.
`.example` und werden nicht in den Betrieb übernommen.

---

## `.env`

Umgebungsvariablen für Backend und Frontend. Wird von Docker Compose eingelesen.

Nicht jede Variable muss gesetzt sein — die meisten haben brauchbare Vorgabewerte.
Zwingend sind nur die im Abschnitt *Basis*. Die vollständige, kommentierte Fassung steht in
`.env.example`; hier stehen zusätzlich die Zusammenhänge.

### Basis

| Variable | Beschreibung | Beispiel |
|----------|-------------|---------|
| `POSTGRES_PASSWORD` | Datenbankpasswort | `openssl rand -base64 32` |
| `DATABASE_URL` | Vollständige Datenbank-URL der Anwendung | `postgresql+asyncpg://postgres:<PW>@db:5432/ggd_ki` |
| `TEST_DATABASE_URL` | Separate Test-DB mit pgvector — nur für Integrationstests | `…/ggd_ki_test` |
| `SCHOOL_SECRET` | HMAC-Schlüssel für Pseudonymisierung — **niemals nach Inbetriebnahme ändern** | `openssl rand -base64 32` |
| `JWT_SECRET` | Schlüssel für JWT-Session-Tokens | `openssl rand -base64 32` |
| `ENVIRONMENT` | `development` oder `production`. In Produktion werden schwache Secrets beim Start abgelehnt | `production` |
| `FRONTEND_ORIGIN` | Öffentliche URL der Plattform (für CORS) | `https://ki.beispielschule.de` |
| `ALLOWED_HOSTS` | Erlaubte `Host`-Header als JSON-Array | `["ki.beispielschule.de"]` |
| `TRUSTED_PROXIES` | Reverse-Proxys, deren `X-Forwarded-For` vertraut wird | `["127.0.0.1","::1"]` |
| `NGINX_PORT` | Host-Port, auf dem nginx lauscht | `8080` |

### LiteLLM-Proxy und Anbieter-Zugänge

Die Schlüssel braucht **nur der Proxy** — das Backend ruft nie direkt einen Anbieter auf.
Es genügen die Zugänge der Anbieter, die in der LiteLLM-Config tatsächlich vorkommen.

| Variable | Beschreibung | Beispiel |
|----------|-------------|---------|
| `LITELLM_PROXY_URL` | Interne URL des Proxys | `http://litellm:4000` |
| `LITELLM_MASTER_KEY` | Zugangsschlüssel für die Admin-API. Muss mit `master_key` der Proxy-Config übereinstimmen | `openssl rand -base64 32` |
| `LITELLM_DATABASE_URL` | **Eigene** Postgres-DB nur für den Proxy (Virtual Keys, Budgets, SpendLogs). Plain `postgresql://`, damit LiteLLMs Prisma-Schema nicht mit dem Alembic-Schema kollidiert | `postgresql://postgres:<PW>@db:5432/litellm` |
| `LITELLM_SALT_KEY` | Verschlüsselt in der DB gespeicherte Credentials. Fest setzen, sonst macht ein späterer Master-Key-Wechsel sie unlesbar | `openssl rand -base64 32` |
| `UI_USERNAME` / `UI_PASSWORD` | Login der Proxy-Admin-UI. Betrifft **nicht** das Schul-Frontend | `admin` |
| `OPENAI_API_KEY` | OpenAI-Zugang | `sk-…` |
| `IONOS_API_KEY` | IONOS-Zugang — der **Value** des Tokens aus dem Data Center Designer, nicht die ID | `eyJ…` |
| `IONOS_API_BASE` | OpenAI-kompatibler Endpunkt von IONOS | `https://openai.inference.de-txl.ionos.com/v1` |
| `LITELLM_PRICE_CURRENCY` | Währung der Preise in der Proxy-Config: `EUR` = keine Umrechnung, `USD` = EUR-Budgets über den EZB-Kurs. **Falsch gesetzt liegt die Kostenrechnung dauerhaft um den Kurs daneben, ohne Fehler** — s. [Vor der Installation](vor-der-installation.md#in-welcher-währung-die-preise-eingetragen-werden) | `EUR` |
| `SPEND_LOG_DELAY` | Wartezeit nach Stream-Ende, bevor die Kosten abgefragt werden | `1.0` |

### Modelle

Die Werte sind die `model_name`s aus der **LiteLLM-Config**, nicht die Modell-IDs der
Anbieter. Sprechende Namen halten einen Anbieterwechsel auf eine Zeile in der Proxy-Config
beschränkt — siehe [Vor der Installation](vor-der-installation.md#modellwahl).

| Variable | Beschreibung | Beispiel |
|----------|-------------|---------|
| `CHAT_DEFAULT_MODEL` | Vorausgewähltes Modell im Chat. Leer = Chats ohne ausdrückliche Wahl schlagen fehl. Muss Function-Calling beherrschen | `chat-standard` |
| `TITLE_MODEL` | Modell für automatische Gesprächstitel. Leer = keine Titel. **Muss in JEDER Team-Allowlist stehen** — der Aufruf läuft über den Virtual Key der Nutzer:innen | `system-titel` |
| `MODEL_PICKER_HIDDEN_PREFIXES` | Präfixe, die nicht im Chat-Modellwähler erscheinen. Rein kosmetisch, Freigaben bleiben unberührt | `["system-","embedding-","bild-"]` |

### Embeddings (Kontextspeicher / semantische Suche)

| Variable | Beschreibung | Beispiel |
|----------|-------------|---------|
| `EMBEDDING_MODEL` | Modell laut LiteLLM-Config | `embedding-standard` |
| `EMBEDDING_DIMENSIONS` | Vektorbreite — **muss zur Datenbankspalte passen**, s. u. | `1024` |
| `EMBEDDING_MAX_CHARS` | Zeichen-Cap je Text vor dem Aufruf | `16000` |
| `EMBEDDING_SEND_DIMENSIONS` | `dimensions`-Parameter mitsenden. Nur OpenAI `text-embedding-3-*` versteht ihn; BGE-M3 lehnt ihn ab | `false` |
| `EMBEDDING_BATCH_SIZE` | Texte je Anfrage im Stapelbetrieb (Backfill, Import). Der Hebel für die Laufzeit: ein Aufruf je Knoten macht aus einem Re-Embedding einen mehrstündigen Lauf | `64` |
| `EMBEDDING_TOKENS_PER_SECOND` | Drosselung nach abgerechnetem Verbrauch; `0` = aus. Das passende Tempo steht im Rate-Limit des eigenen Anbieterkontos | `3000` |
| `EMBEDDING_MAX_RETRIES` | Wiederholungen bei 429/503 | `3` |
| `EMBEDDING_RETRY_MAX_WAIT_S` | Obergrenze je Wartezeit — begrenzt, wie lange ein Knoten-Anlegen im Request hängt | `5.0` |

### Bildgenerierung

| Variable | Beschreibung | Beispiel |
|----------|-------------|---------|
| `IMAGE_DEFAULT_MODEL` | Bildmodell laut LiteLLM-Config (braucht dort `model_info.mode: image_generation`) | `bild-standard` |
| `IMAGE_GENERATION_TIMEOUT` | Zeitbudget je Bild in Sekunden | `120.0` |
| `IMAGE_MODELS_PATH` | Pfad zur **Bildarten**-Datei. Wer mehr als ein Bildmodell nutzt, legt sie aus `config/image_models.example.yaml` an; s. [Modelle & Assistenten](modelle-und-assistenten.md#bildarten-festlegen-configimage_modelsyaml) | `config/image_models.yaml` |
| `IMAGE_SIZES` | Benannte Formate als JSON-Objekt Name→Pixelgröße. **Nur wirksam, solange keine Bildarten-Datei existiert** | `{"quadratisch":"1024x1024",…}` |
| `IMAGE_DEFAULT_FORMAT` | Standardformat — muss ein Schlüssel aus `IMAGE_SIZES` sein (wird beim Start geprüft). Von den Bildarten abgelöst | `quadratisch` |
| `IMAGE_RESPONSE_FORMAT` | Leer = Parameter weglassen (gpt-image-1, FLUX); `b64_json` = Base64 erzwingen, wo sonst eine URL käme. Von den Bildarten abgelöst | *(leer)* |
| `IMAGE_PRICES` | **Pflicht für jedes Modell, das eine Bildart nennt.** LiteLLM ignoriert für Bilder den Preis aus der Config — ohne diese Variable kostet jedes Bild 0,00 $ und läuft am Budget vorbei. In **einfachen** Anführungszeichen! | `'{"black-forest-labs/FLUX.1-schnell":0.032}'` |

> Die vier Variablen `IMAGE_DEFAULT_MODEL`, `IMAGE_SIZES`, `IMAGE_DEFAULT_FORMAT` und
> `IMAGE_RESPONSE_FORMAT` beschreiben **ein** Bildmodell. Sobald `config/image_models.yaml`
> existiert, stammen diese Angaben aus den Bildarten und die Variablen bleiben ungenutzt.
> Ohne die Datei wird aus ihnen genau eine Bildart gebildet — bestehende Installationen
> ändern sich durch das Update also nicht.

### Jugendschutz-Klassifikator

| Variable | Beschreibung | Beispiel |
|----------|-------------|---------|
| `GUARDRAIL_HEALTH_FILE` | Zustandsbericht des Guardrails. Muss auf **dieselbe Datei** zeigen wie `health_file` in der LiteLLM-Config, s. [Content-Moderation](content-moderation.md) | `data/guardrail_health.json` |
| `GUARDRAIL_HEALTH_MAX_AGE_H` | Ab diesem Alter gilt der Bericht als veraltet und nicht mehr als gesund | `24` |

### Pfade zu Konfigurationsdateien

| Variable | Beschreibung | Beispiel |
|----------|-------------|---------|
| `AUTH_CONFIG_PATH` | Pfad zur auth.yaml | `config/auth.yaml` |
| `BUDGET_TIERS_PATH` | Pfad zur budget_tiers.yaml | `config/budget_tiers.yaml` |
| `CRISIS_TRIGGERS_PATH` | Pfad zur crisis_triggers.yaml | `config/crisis_triggers.yaml` |
| `HELP_RESOURCES_PATH` | Pfad zur help_resources.yaml | `config/help_resources.yaml` |
| `PEDAGOGY_PATH` | Pfad zur pedagogy.yaml | `config/pedagogy.yaml` |

### Anmeldung, Schule, Darstellung

| Variable | Beschreibung | Beispiel |
|----------|-------------|---------|
| `AUTH_ISERV_CLIENT_SECRET` | OAuth2-Client-Secret des SSO-Providers | *(vom Provider)* |
| `AUTH_DEBUG_USERINFO` | Loggt die Claims des SSO-Providers beim Login — zur Diagnose fehlender Gruppen. **In Produktion aus** | `false` |
| `PUBLIC_STUDENT_GRADES` | Jahrgangsstufen als JSON-Array | `[5,6,7,8,9,10,11,12]` |
| `PUBLIC_PERIODS` | Stundenraster der Schule (Wochenmuster-Editor); ausgelassene Stunden weglassen | `[1,2,3,4,5,6,8,9]` |
| `SCHULART` | Schulart — steuert die Auswahl der Bildungspläne | `GYM` |
| `EXPORT_SCHOOL_NAME` | Schulname in PDF-/DOCX-Exporten. Leer = `PUBLIC_SCHOOL_NAME` | `Beispielschule` |
| `PUBLIC_SCHOOL_NAME` | Anzeigename der Plattform | `ki@beispielschule` |
| `PUBLIC_SCHOOL_LOGO_URL` | Logo-URL (Fallback für beide Themes) | *(leer → Initialen)* |
| `PUBLIC_SCHOOL_LOGO_URL_LIGHT` | Logo für helles Theme | `/static/logo-light.png` |
| `PUBLIC_SCHOOL_LOGO_URL_DARK` | Logo für dunkles Theme | `/static/logo-dark.png` |

### Stundenplan (optional)

| Variable | Beschreibung | Beispiel |
|----------|-------------|---------|
| `WEBUNTIS_SERVER` | Stundenplan-Server. **Leer = Integration aus**, s. [Stundenplan-Integration](stundenplan-integration.md) | `ggd.webuntis.com` |
| `WEBUNTIS_USER` | Benutzername des technischen Servicekontos | *(vom Stundenplan-Admin)* |
| `WEBUNTIS_PASSWORD` | Passwort des Servicekontos | *(vom Stundenplan-Admin)* |
| `WEBUNTIS_SCHOOL` | Schulkürzel — **nur bei geteiltem Server**; bei eigener Subdomain leer lassen | *(leer)* |


> **Wichtig:** `SCHOOL_SECRET` darf nach der ersten Inbetriebnahme nie geändert
> werden. Alle Pseudonyme würden sich dadurch ändern — bestehende Nutzerkonten
> und Gesprächsverläufe wären nicht mehr zuordenbar.

### Modelle wechseln

Alle Modellnamen oben sind die Namen, unter denen der **LiteLLM-Proxy** die Modelle führt —
nicht die IDs der Anbieter. Ein Modellwechsel ist damit Konfigurationsarbeit: Eintrag in der
`model_list` des Proxys anpassen bzw. ergänzen, Variable in `.env` umstellen, Backend neu
starten. Für Chat-, Titel- und Bildmodelle ist das alles.

> ⚠️ **`EMBEDDING_DIMENSIONS` ist die Ausnahme.** Der Wert muss zur Spaltenbreite von
> `context_nodes.embedding` passen. Ihn zu ändern heißt: Schema angleichen **und** alle
> Knoten neu einbetten — Vektoren verschiedener Modelle sind nicht vergleichbar, es gibt
> kein Umrechnen. Während der Umstellung liefert die semantische Suche keine Treffer.
> Ablauf: **[Runbook: Embedding-Modell wechseln](../runbooks/modellwechsel.md)**.
>
> Passen Konfiguration und Spalte nicht zusammen, bricht die Embedding-Generierung mit einer
> `EmbeddingDimensionError` ab, die beide Breiten und den Modellnamen nennt — das Anlegen von
> Knoten schlägt dadurch aber nicht fehl (Embedding ist kein kritischer Pfad).

Damit Kosten und Budgets greifen, braucht **jedes** Modell in der LiteLLM-Config
`model_info.input_cost_per_token` / `output_cost_per_token`. Für Modelle, die LiteLLM nicht
aus seiner eingebauten Preistabelle kennt (alles, was über `openai/<id>` mit eigener
`api_base` läuft), bleibt der Spend sonst bei **0** — Budget-Tiers und Kostenstatistik
laufen dann ins Leere.

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

> **Hinweis:** Das Client-Secret des SSO-Providers wird **nicht** in dieser Datei
> gespeichert, sondern über die Umgebungsvariable `AUTH_ISERV_CLIENT_SECRET` in
> `.env` übergeben.

### SSO-Rollen/-Gruppen einrichten und diagnostizieren

Welche Namen in `group_role_map` und in die `groups`-Muster gehören, hängt davon
ab, was der SSO-Provider tatsächlich liefert. Dafür gibt es drei eingebaute
Diagnose-Hilfen:

1. **Profil → „SSO-Mitgliedschaften (Diagnose)"** — für jede angemeldete Person
   sichtbar. Zeigt die rohen, vom SSO gelieferten Gruppen und Rollen sowie die
   daraus abgeleiteten Plattform-Rollen. Erste Anlaufstelle bei falscher Rolle:
   die angezeigten Namen 1:1 (Schreibweise egal) in `group_role_map` übernehmen.
2. **Server-Log bei jedem Login** (immer aktiv, ohne personenbezogene Werte):
   ```
   OAuth-Login: userinfo-Claims=[…], groups=8, sso_roles=['ROLE_TEACHER'] → Rollen=['teacher']
   ```
   Zeigt, welche Claim-Keys ankommen, wie viele Gruppen erkannt wurden und welche
   Plattform-Rollen herauskommen.
3. **`AUTH_DEBUG_USERINFO=true`** (in `.env`, danach Backend neu starten) — loggt
   zusätzlich die **komplette userinfo** inklusive Werten; nützlich, um Key-Namen
   und Datenstruktur zu sehen. **Enthält Klarnamen/E-Mail → nur temporär aktivieren.**

Schlägt der Login mit „Anmeldung vom Schulkonto abgelehnt: …" bzw. „Missing code
or state" fehl, loggt der Callback den vom Provider gemeldeten OAuth-`error`
(häufig `invalid_scope` → falscher oder nicht freigeschalteter Scope-Name).

> **IServ-Spezifika.** Damit die Diagnose im Regelfall gar nicht nötig ist — diese
> Werte liefert IServ konkret:
> - **Scopes** tragen das Präfix `iserv:` → `iserv:groups`, `iserv:roles`
>   (`groups`/`roles` ohne Präfix ⇒ „scope not allowed"). Die Scopes müssen am
>   OAuth-Client in IServ freigeschaltet sein.
> - **Rollen** kommen als Symfony-Tokens **`ROLE_TEACHER`, `ROLE_STUDENT`,
>   `ROLE_ADMIN`** (nicht „Lehrer"/„Schüler") — genau diese in `group_role_map`
>   mappen. `ROLE_ADMIN` bewusst nicht auf `admin` legen (sonst ist jede:r
>   IServ-Admin Plattform-Admin); dafür eine eigene Gruppe verwenden.
> - **Gruppen** kommen als Objekte; maßgeblich ist der **Account-Name (`act`)** in
>   Kleinschreibung mit Punkt-Notation: `kollegium`, `fs.mathematik`, `klasse.8d`.
>   Genau diese Form treffen die `groups`-Muster (`^FS\.(.+)$` …) und die
>   `group_role_map`.

> **Wichtig:** Nach jeder Änderung an `scope` oder `group_role_map` müssen sich die
> Betroffenen **neu anmelden** — Rollen und Gruppen stecken im 30-Tage-Session-Cookie.

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
docker compose exec backend python scripts/monthly_team_reconcile.py
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

Konfiguriert den LiteLLM-Proxy: welche Modelle verfügbar sind, über welche Anbieter sie
laufen, was sie kosten und welche Guardrails greifen. **Zwei fertige Vorlagen** liegen bei:

| Vorlage | Für wen |
|---|---|
| `infra/litellm_config.example.yaml` | Allgemein, mit OpenAI als Beispielanbieter |
| `infra/litellm_config.ionos.example.yaml` | EU-Betrieb mit IONOS — vollständig ausgefüllt, Modell-IDs und Preise gemessen |

### Das Namensschema

Die `model_name`s sind das, was `.env`, Assistenten und Team-Allowlists ansprechen — und
was Nutzer:innen im Modellwähler lesen. Deshalb **Aufgaben statt Produktnamen**: Ein
Anbieterwechsel ändert dann nur `litellm_params.model` in dieser Datei.

```yaml
model_list:
  - model_name: chat-standard            # = CHAT_DEFAULT_MODEL
    litellm_params:
      model: openai/<anbieter-modell-id>
      api_base: os.environ/IONOS_API_BASE     # entfällt bei OpenAI
      api_key: os.environ/IONOS_API_KEY
    model_info:
      supports_function_calling: true    # PFLICHT, sonst fallen alle Funktionen stumm aus
      input_cost_per_token: 0.00000017   # PFLICHT, sonst bleibt der Spend 0
      output_cost_per_token: 0.00000071

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY   # = LITELLM_MASTER_KEY in .env
  database_url: os.environ/LITELLM_DATABASE_URL
```

Bewährt hat sich eine Staffel nach Aufgabe — `chat-schnell`, `chat-standard`, `chat-code`,
`chat-reasoning`, `chat-komplex` — plus interne Modelle unter dem Präfix `system-`
(`system-titel`, `system-moderation`), die `MODEL_PICKER_HIDDEN_PREFIXES` aus dem
Modellwähler ausblendet. Welche Modelle sich wofür eignen, steht in
[Vor der Installation](vor-der-installation.md#modellwahl).

### Drei Dinge, die still schiefgehen

| | Folge, wenn es fehlt |
|---|---|
| `supports_function_calling: true` | Wissensgraph, Unterrichtsplanung und Bildgenerierung fallen ersatzlos aus. Das Modell antwortet freundlich und ruft nie eine Funktion auf. |
| `input_cost_per_token` / `output_cost_per_token` | Der SpendLog meldet 0. EUR-Budgets, die 429-Sperre und die Kostenstatistik laufen ins Leere. Betrifft **jedes** Modell mit eigener `api_base` — LiteLLM kennt dafür keine Preise. |
| `IMAGE_PRICES` in der `.env` | Für **Bilder** ignoriert LiteLLM den Preis aus dieser Datei und liest nur seine eingebaute Tabelle. Ohne die Variable kostet jedes Bild 0,00 $. |

> **Prüfen statt hoffen:** `cd backend && python scripts/check_litellm_config.py` gleicht den
> laufenden Proxy gegen die `.env` ab und meldet genau diese Fälle — fehlende Preise,
> fehlendes `supports_function_calling`, falsche `mode`, unbekannte Modellnamen und nicht
> ersetzte Platzhalter.

### Guardrails

Der `guardrails:`-Block gehört auf die **oberste Ebene** der Datei, nicht unter
`litellm_settings` — dort erwartet LiteLLM ein älteres Format und der Proxy startet nicht.
Die mitgelieferten Vorlagen nutzen einen LLM-Klassifikator, der vier Kategorien in einem
Aufruf bewertet und mit jedem Anbieter funktioniert. Einzelheiten, Verhalten bei Störungen
und die Überwachung: [Content-Moderation & Guardrails](content-moderation.md).

Die vollständige Referenz für `model_list` und Anbieter-Konfigurationen findet sich in der
[LiteLLM-Dokumentation](https://docs.litellm.ai).
