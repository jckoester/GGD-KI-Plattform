# Backend-Entwicklung

## Datenbank-Migrationen (Alembic)

Migrationen liegen in `backend/alembic/versions/`. Alembic vergleicht die
SQLAlchemy-Modelle (`app/db/models.py`) mit dem DB-Schema und generiert
daraus Migrationsskripte.

```bash
# Aktuelle Migration anwenden
alembic upgrade head

# Nach einer Modelländerung: Migration generieren
alembic revision --autogenerate -m "kurze beschreibung der aenderung"

# Einen Schritt zurückrollen
alembic downgrade -1

# Aktuellen Migrations-Stand anzeigen
alembic current
```

**Generierte Migrationen immer vor dem Commit prüfen.** `autogenerate` erkennt
nicht alles zuverlässig — insbesondere CHECK-Constraints, benutzerdefinierte
Datentypen und Index-Optionen können fehlen oder falsch sein.

## Tests

### Struktur

```
backend/tests/
├── unit/               Unittests ohne DB-Zugriff
│   ├── conftest.py     Absichtlich leer (verhindert übergeordnete Fixtures)
│   └── test_*.py
└── test_db_*.py        Manuelle DB-Tests (nicht in CI)
```

### Unittests ausführen

```bash
cd backend
pytest tests/unit -v

# Mit Coverage
pytest tests/unit --cov=app --cov-report=term-missing
```

Die `tests/unit/conftest.py` ist **absichtlich leer**. Das verhindert, dass
ein übergeordneter `conftest.py` DB-Fixtures einschleust und Unittests
ungewollt datenbankabhängig macht.

### Abhängigkeiten mocken

Für HTTP-Calls (LiteLLM-Client, ECB-API) wird `pytest-httpx` verwendet:

```python
from pytest_httpx import HTTPXMock

def test_something(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url="http://...", json={"key": "value"})
    # ... Code aufrufen, der httpx verwendet
```

### Integrationstests

Integrationstests (`testcontainers[postgresql]`) sind vorbereitet, aber noch
nicht vollständig ausgebaut. Sie starten eine echte PostgreSQL-Instanz in
Docker und testen End-to-End. Ausführung setzt Docker voraus.

## Skripte (`backend/scripts/`)

Alle Skripte sind eigenständig ausführbar und können sowohl direkt als auch
im Container aufgerufen werden:

```bash
# Lokal (venv aktiv)
python scripts/<skript>.py

# Im Container
docker compose exec backend python scripts/<skript>.py
```

| Skript | Zweck | Flags |
|--------|-------|-------|
| `create_litellm_teams.py` | LiteLLM-Teams einmalig anlegen (idempotent) | — |
| `monthly_budget_reconcile.py` | EUR-Budgets → USD-Limits in LiteLLM setzen | — |
| `refresh_ecb_rate.py` | ECB-Wechselkurs abrufen und in DB speichern | — |
| `seed_exchange_rate.py` | Wechselkurs für frische DB setzen (einmalig) | — |
| `cleanup_inactive_accounts.py` | Konten ohne Login > 90 Tage löschen | `--dry-run`, `--now`, `--limit` |
| `cleanup_stale_conversations.py` | Konversationen ohne Nachrichten > 93 Tage löschen | `--dry-run`, `--now` |

`--dry-run` gibt aus, was gelöscht würde, ohne etwas zu löschen.
`--now <ISO-Timestamp>` simuliert einen anderen „Jetzt"-Zeitpunkt —
nützlich für Tests und für den Schuljahreswechsel.
