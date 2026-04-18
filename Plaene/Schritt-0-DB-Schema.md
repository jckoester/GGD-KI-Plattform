# Schritt 0 — DB-Schema

## Kontext

Vor der Authentifizierung (Schritt 1) muss das Datenbankschema stehen. Das betrifft 8 Tabellen aus ADR-003 und ADR-005, eine laufende Async-SQLAlchemy-Session, Alembic für Migrationen und eine `.env.example` als Konfigurationsvorlage. Entwicklung läuft lokal ohne Docker — PostgreSQL muss lokal laufen.

---

## Dateien

| Datei | Aktion |
|-------|--------|
| `backend/requirements.txt` | Alle Abhängigkeiten (inkl. spätere Schritte) |
| `backend/app/config.py` | Pydantic-Settings für alle Env-Variablen |
| `backend/app/db/models.py` | SQLAlchemy 2.0 ORM — alle 8 Tabellen |
| `backend/app/db/session.py` | Async Engine, SessionLocal, `get_db` Dependency |
| `backend/alembic.ini` | Alembic-Konfiguration (neu, per `alembic init`) |
| `backend/alembic/env.py` | Async-Migration-Setup mit Modellen |
| `backend/alembic/versions/0001_initial_schema.py` | Erste Migration (autogeneriert) |
| `.env.example` | Alle benötigten Umgebungsvariablen |
| `backend/tests/__init__.py` | leer |
| `backend/tests/conftest.py` | pytest-Fixtures: testcontainers DB, async Session |
| `backend/tests/test_schema.py` | Schema-Smoke-Tests |

---

## 1. `backend/requirements.txt`

```
# Runtime
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
pydantic>=2.7.0
pydantic-settings>=2.3.0
sqlalchemy[asyncio]>=2.0.30
asyncpg>=0.29.0
alembic>=1.13.0
python-dotenv>=1.0.0
pyyaml>=6.0.1
python-jose[cryptography]>=3.3.0
httpx>=0.27.0

# Dev / Test
pytest>=8.0.0
pytest-asyncio>=0.23.0
testcontainers[postgresql]>=4.7.0
```

---

## 2. `backend/app/config.py`

`pydantic_settings.BaseSettings` mit folgenden Feldern:

| Feld | Typ | Default |
|------|-----|---------|
| `database_url` | `str` | — |
| `school_secret` | `str` | — |
| `jwt_secret` | `str` | — |
| `litellm_proxy_url` | `str` | `http://localhost:4000` |
| `litellm_master_key` | `str` | `""` |
| `frontend_origin` | `str` | `http://localhost:5173` |
| `environment` | `str` | `development` |
| `auth_config_path` | `str` | `config/auth.yaml` |
| `budget_tiers_path` | `str` | `config/budget_tiers.yaml` |
| `auth_iserv_client_secret` | `str` | `""` |

`env_file = ".env"`, `case_sensitive = False`.

---

## 3. `backend/app/db/models.py` — 8 Tabellen

Alle Modelle erben von `Base = DeclarativeBase()`.

**`subjects`** — `id` SERIAL PK, `slug` UNIQUE, `min_grade`/`max_grade` INT nullable, `sort_order` DEFAULT 0

**`assistants`** — FK → subjects, `status` CHECK IN (`draft`,`active`,`disabled`,`archived`) DEFAULT `draft`, `force_cost_display` BOOLEAN DEFAULT FALSE, `created_by_pseudonym` nullable TEXT (kein FK)

**`conversations`** — UUID PK, `pseudonym` TEXT NOT NULL (kein FK), FK → subjects + assistants (beide nullable), `system_prompt_snapshot` nullable, `total_cost_usd` NUMERIC(10,6) DEFAULT 0; Index auf `pseudonym` und `last_message_at`

**`messages`** — UUID PK, FK → conversations ON DELETE CASCADE, `role` CHECK IN (`user`,`assistant`), cost/token-Felder nullable (nur für role=`assistant`); Index auf `conversation_id`

**`user_preferences`** — `pseudonym` TEXT PK, `preferences` JSONB DEFAULT `{}`

**`pseudonym_audit`** — `pseudonym` TEXT PK, `role`, `grade` nullable, `created_at`/`last_login_at` TIMESTAMPTZ NOT NULL, `revoked_all_before` TIMESTAMPTZ nullable

**`jwt_revocations`** — `jti` TEXT PK, `pseudonym` NOT NULL, `expires_at` NOT NULL, `reason` nullable; Index auf `pseudonym` und `expires_at`

**`exchange_rates`** — SERIAL PK, `eur_usd_rate` NUMERIC(10,6), `source` TEXT (`ECB`|`manual`), `effective_from` TIMESTAMPTZ; Index auf `effective_from`

---

## 4. `backend/app/db/session.py`

```python
engine = create_async_engine(settings.database_url)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncIterator[AsyncSession]: ...
```

Kein `create_all` — Schema kommt ausschließlich über Alembic.

---

## 5. Alembic-Setup

```bash
cd backend
alembic init alembic
```

`alembic/env.py` anpassen für:
- Async Engine (`run_async_migrations`-Pattern)
- `target_metadata = Base.metadata`
- `sqlalchemy.url` aus `settings.database_url`

```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

---

## 6. `.env.example`

```dotenv
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ggd_ki
SCHOOL_SECRET=           # openssl rand -base64 32
JWT_SECRET=              # openssl rand -base64 32
LITELLM_PROXY_URL=http://localhost:4000
LITELLM_MASTER_KEY=
FRONTEND_ORIGIN=http://localhost:5173
ENVIRONMENT=development
AUTH_CONFIG_PATH=config/auth.yaml
BUDGET_TIERS_PATH=config/budget_tiers.yaml
AUTH_ISERV_CLIENT_SECRET=   # nur in Produktion setzen
```

---

## 7. Tests

### `backend/tests/conftest.py`
- `db_engine` — startet testcontainers PostgreSQL, führt `alembic upgrade head` aus
- `db_session` — `AsyncSession` gegen Test-DB
- `TEST_SCHOOL_SECRET = "test-secret-not-for-production-000000000000"`

### `backend/tests/test_schema.py`
1. Alle 8 Tabellen existieren nach Migration
2. CRUD-Roundtrip: `Subject` anlegen, lesen, löschen
3. Cascade-Delete: `Conversation` löschen → `Messages` verschwinden
4. CHECK-Constraint: `assistants.status` ungültig → IntegrityError
5. CHECK-Constraint: `messages.role` ungültig → IntegrityError

---

## Verifikation

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env  # Werte eintragen
alembic upgrade head
pytest tests/test_schema.py -v
```
