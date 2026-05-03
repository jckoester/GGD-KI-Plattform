# Lokales Dev-Setup

Die Entwicklung läuft lokal ohne Docker Compose. Backend und Frontend werden
direkt gestartet; LiteLLM läuft entweder lokal oder ist im lokalen Netz
erreichbar.

## Voraussetzungen

- Python 3.10+ (`python3 --version`)
- Node.js 20+ (`node --version`)
- PostgreSQL erreichbar (lokal installiert oder als einzelner Docker-Container)
- LiteLLM (lokal oder im Netz)

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

# Abhängigkeiten installieren
pip install -r requirements.txt

# Konfiguration anlegen
cp config/.env.example config/.env
```

Minimale `.env` für die lokale Entwicklung:

```
POSTGRES_PASSWORD=devpassword
DATABASE_URL=postgresql+asyncpg://postgres:devpassword@localhost:5432/ggd_ki
SCHOOL_SECRET=dev-school-secret-not-for-production
JWT_SECRET=dev-jwt-secret-not-for-production
LITELLM_PROXY_URL=http://localhost:4000
LITELLM_MASTER_KEY=sk-dev
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
