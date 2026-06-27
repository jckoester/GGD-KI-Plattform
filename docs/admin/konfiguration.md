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
