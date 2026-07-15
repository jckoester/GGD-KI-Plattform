# Lokales Dev-Setup

Die Entwicklung läuft lokal ohne Docker Compose. Backend und Frontend werden
direkt gestartet; der LiteLLM-Proxy läuft als Prozess in der backend-venv (siehe
[LiteLLM lokal starten](#litellm-lokal-starten)).

## Voraussetzungen

- Python 3.10+ (`python3 --version`)
- Node.js 20+ (`node --version`)
- PostgreSQL erreichbar (lokal installiert oder als einzelner Docker-Container)
- LiteLLM-Proxy lokal in der backend-venv (Abschnitt unten)
- Optional: Ollama für den self-hosted Fallback (`ollama serve`)

PostgreSQL als Docker-Container (ohne Compose):
```bash
docker run -d --name ki-postgres \
  -e POSTGRES_PASSWORD=devpassword \
  -e POSTGRES_DB=ggd_ki \
  -p 5432:5432 \
  postgres:16-alpine
```

## Backend

```bash
cd backend

# Virtuelle Umgebung anlegen und aktivieren
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Abhängigkeiten installieren (inkl. spaCy + deutschem NER-Modell ~45 MB
# für die PII-Erkennung — als gepinntes Wheel in requirements.txt verankert)
pip install -r requirements.txt

# Konfiguration anlegen
cp .env.example .env
```

> **Hinweis (PII-Modell):** Das deutsche NER-Modell `de_core_news_md` wird über eine
> gepinnte Wheel-URL in `requirements.txt` mitinstalliert — **nicht** über
> `python -m spacy download` (das scheitert in uv-/manchen Umgebungen). Schlägt der
> Wheel-Download fehl, das Wheel manuell laden und `pip install <pfad>.whl` ausführen.

Minimale `.env` für die lokale Entwicklung:

```
POSTGRES_PASSWORD=devpassword
DATABASE_URL=postgresql+asyncpg://postgres:devpassword@localhost:5432/ggd_ki
SCHOOL_SECRET=dev-school-secret-not-for-production
JWT_SECRET=dev-jwt-secret-not-for-production
LITELLM_PROXY_URL=http://localhost:4000
LITELLM_MASTER_KEY=sk-dev
OPENAI_API_KEY=sk-...               # Provider-Key, den der lokale Proxy nutzt
OLLAMA_BASE_URL=http://localhost:11434
LITELLM_DATABASE_URL=postgresql://postgres:devpassword@localhost:5432/litellm
CHAT_DEFAULT_MODEL=gpt-4o-mini
TITLE_MODEL=gpt-4o-mini
FRONTEND_ORIGIN=http://localhost:5173
ENVIRONMENT=development
AUTH_CONFIG_PATH=config/auth.yaml
BUDGET_TIERS_PATH=config/budget_tiers.yaml
PUBLIC_SCHOOL_NAME=ki@schule
```

```bash
# Datenbank-Migration
alembic upgrade head

# Entwicklungsserver starten (auto-reload bei Dateiänderungen)
uvicorn app.main:app --reload
# Backend läuft auf http://localhost:8000
# API-Doku: http://localhost:8000/docs
```

## LiteLLM lokal starten

Früher zeigte `LITELLM_PROXY_URL` auf den im Homelab gehosteten Proxy
(`https://alan-dev.jckoester.de`). Im Dev-Setup läuft LiteLLM stattdessen lokal
als Prozess in der backend-venv auf `http://localhost:4000`. Das Backend spricht
den Proxy sowohl über die Management-API (User/Teams/Keys/Budgets/SpendLogs) als
auch über die OpenAI-kompatiblen Endpunkte (`/chat/completions`, `/embeddings`)
an — beides braucht einen **DB-gestützten** Proxy.

### 1. Proxy-Abhängigkeiten installieren

Das Backend importiert `litellm` nicht (nur HTTP), daher steht es nicht in
`backend/requirements.txt`. Der Proxy inkl. Prisma bekommt eine **eigene venv**.

> **⚠ Nicht die backend-venv verwenden.** Die läuft auf Python 3.14; Proxy-Deps
> wie `orjson` haben dafür keine vorgebauten Wheels und scheitern beim
> Rust/PyO3-Build (`PyO3's maximum supported version (3.13)`). Deshalb eine
> dedizierte venv auf **Python 3.13** (oder ≤3.13) — dort gibt es Binär-Wheels,
> kein Compiler/Rust-Toolchain nötig.

```bash
# aus dem Repo-Root:
python3.13 -m venv infra/litellm-venv
source infra/litellm-venv/bin/activate
pip install -r infra/litellm-requirements.txt

# Prisma-Client einmalig erzeugen. Wichtig: --schema auf LiteLLMs mitgeliefertes
# Schema zeigen (nacktes `prisma generate` sucht im Projektordner und findet es
# nicht). Pfad versionsunabhängig auflösen:
SCHEMA=$(python -c "import litellm, os; print(os.path.join(os.path.dirname(litellm.__file__), 'proxy', 'schema.prisma'))")
prisma generate --schema="$SCHEMA"
```

Die venv `infra/litellm-venv/` ist in `.gitignore` ausgenommen. Das Start-Skript
(Schritt 4) aktiviert die venv **und** generiert den Prisma-Client automatisch,
falls er noch fehlt — die beiden Zeilen oben sind also optional, aber nützlich
zum Verifizieren.

> **Warum `prisma` extra?** Bei LiteLLM 1.83.7 hängt `prisma` am Extra
> `extra-proxy`, nicht an `proxy` — `litellm[proxy]` allein lässt den Proxy mit
> `ModuleNotFoundError: No module named 'prisma'` abbrechen. Deshalb ist
> `prisma==0.11.0` in `infra/litellm-requirements.txt` explizit gepinnt.

### 2. Eigene Postgres-DB für den Proxy anlegen

LiteLLM legt seine Tabellen (Virtual Keys, Teams, Budgets, SpendLogs) über
Prisma an. Dafür eine **separate** Datenbank verwenden — nicht die App-DB, damit
sich Prisma- und Alembic-Schema nicht in die Quere kommen:

```bash
createdb -U postgres litellm
# oder in psql:  CREATE DATABASE litellm;
```

`LITELLM_DATABASE_URL` in `.env` muss ein **plain** `postgresql://`-DSN sein
(nicht der `postgresql+asyncpg://`-DSN des Backends).

### 3. Config anlegen

```bash
cp infra/litellm_config.dev.example.yaml infra/litellm_config.dev.yaml
```

Die Dev-Config exponiert die Modellnamen, die der Code erwartet: `gpt-4`
(Chat/Titel), `text-embedding-3-small` (in `app/context/embedding.py`
fest verdrahtet), `gpt-image-1.5` (Bild, optional) sowie `ollama-fallback`.
Die Jugendschutz-Guardrails aus `infra/litellm_config.example.yaml` (Produktion)
sind hier bewusst weggelassen.

### 4. Proxy starten

Am einfachsten über das Start-Skript (lädt `.env`, aktiviert die venv, prüft
Pflicht-Variablen):

```bash
./infra/litellm_start_dev.sh          # Port 4000; PORT=… / CONFIG=… überschreibbar
```

Oder von Hand:

```bash
# aus dem Repo-Root, Proxy-venv aktiviert:
source infra/litellm-venv/bin/activate
set -a && source .env && set +a          # OPENAI_API_KEY, LITELLM_MASTER_KEY, … exportieren
litellm --config infra/litellm_config.dev.yaml --port 4000
```

### 5. Prüfen

```bash
# Modelle sichtbar? (Master-Key aus .env)
curl -s http://localhost:4000/models -H "Authorization: Bearer $LITELLM_MASTER_KEY"

# Chat-Completion durchreichen
curl -s http://localhost:4000/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"ping"}]}'
```

Liefern beide Aufrufe eine sinnvolle Antwort, kann das Backend gestartet werden.
Zum schnellen Zurückschalten auf den Homelab-Proxy die auskommentierte
`LITELLM_PROXY_URL`-Zeile in `.env` wieder aktivieren.

### Admin-UI des Proxys (optional)

Der Proxy bringt eine eigene Admin-UI unter `http://localhost:4000/ui` mit
(Keys, Teams, Budgets, SpendLogs einsehen). Der Login ist standardmäßig:

- **Username:** `admin`
- **Passwort:** der Wert von `LITELLM_MASTER_KEY`

Häufiger Stolperstein: Der Master-Key gehört ins **Passwort**-Feld, nicht ins
Username-Feld. Wer lieber einen kurzen Dev-Login statt des langen Keys möchte,
setzt in `.env` `UI_USERNAME`/`UI_PASSWORD` und startet den Proxy neu:

```
UI_USERNAME=admin
UI_PASSWORD=dev
```

Diese UI betrifft **nur** den Proxy. Der Login der GGD-KI-Plattform selbst
(`http://localhost:5173`) läuft unabhängig davon über den `yaml_test`-Adapter
(siehe [Test-Authentifizierung](#test-authentifizierung)).

**Persistenz von UI-Einträgen:** Über die UI angelegte Modelle/Credentials
überleben einen Neustart nur, wenn `store_model_in_db: true` in
`general_settings` gesetzt ist (in der Dev-Config bereits aktiv). Ohne die
Option leben sie nur im Speicher und sind nach dem Stopp weg. Die statische
`model_list` in der Config bleibt davon unberührt; die UI-Einträge kommen
additiv aus der DB dazu. Die api_keys der Credentials werden verschlüsselt
gespeichert — der Schlüssel ist `LITELLM_SALT_KEY` (Fallback: `LITELLM_MASTER_KEY`).
Wird der Master-Key rotiert, ohne dass ein fester `LITELLM_SALT_KEY` gesetzt ist,
sind bereits gespeicherte Credentials nicht mehr entschlüsselbar — für stabile
Dev-Umgebungen daher am besten einen festen `LITELLM_SALT_KEY` setzen.

## Frontend

```bash
cd frontend

npm install

npm run dev
# Frontend läuft auf http://localhost:5173
# /api wird automatisch an http://localhost:8000 proxied (vite.config.js)
```

## Test-Authentifizierung

Für die lokale Entwicklung den `yaml_test`-Adapter verwenden — kein SSO-Provider
erforderlich, Login über ein einfaches Formular.

`config/auth.yaml`:
```yaml
adapter: yaml_test
yaml_test:
  users_file: config/test_users.yaml
```

`config/test_users.yaml` aus der Beispieldatei anlegen:
```bash
cp config/test_users.example.yaml config/test_users.yaml
```

Die Beispieldatei enthält bereits Testnutzer für alle Rollen. Der Login
erfolgt über die normale Login-Seite der Plattform mit Benutzername und Passwort.

## Typ-Prüfung und Linting

```bash
# Frontend: Svelte-Typen prüfen
cd frontend && npm run check

# Frontend: ESLint
cd frontend && npm run lint

# Backend: keine automatische Typ-Prüfung konfiguriert (mypy optional)
```
