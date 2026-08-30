# Systemarchitektur

## Komponenten-Übersicht

```
Browser
  └─▶ nginx (Port 80, TLS-Terminierung extern via Caddy o. ä.)
        ├─▶ /          → Frontend (SvelteKit, Node)
        └─▶ /api/      → Backend (FastAPI, uvicorn)
                              ├─▶ PostgreSQL  (Nutzer, Konversationen, Budgets)
                              └─▶ LiteLLM     (KI-Proxy, Budget-Enforcement)
                                    └─▶ KI-Anbieter  (IONOS, Mistral, OpenAI, Anthropic, …)

Cron-Container (separat):
  cleanup_inactive_accounts     täglich 02:00
  cleanup_stale_conversations   täglich 02:30
  refresh_ecb_rate              1. des Monats 06:00
  monthly_team_reconcile        1. des Monats 07:00
  weekly_budget_accrual         montags 05:00
```

## Backend-Module (`backend/app/`)

| Modul | Zweck |
|-------|-------|
| `auth/` | OAuth2/OIDC-Flow, JWT-Ausgabe und -Prüfung, Pseudonymisierung, Adapter-Interface |
| `chat/` | Chat-Endpunkte, SSE-Streaming, Konversations- und Nachrichtenverwaltung, Tool-Registry (`tools.py`: `planning` / `student_planning`) |
| `context/` | Kontextspeicher: Knoten/Kanten, Curriculum-Import, Retrieval (semantisch + Engagement-UNION), Taxonomie |
| `planning/` | Unterrichtsplanung (UP-Reihe): Slots/Snapshots, Jahresplan- und Stundenentwurfs-Logik, Assistenten-Tools. Verschiebe-Dialog: `reflow_service.py` (Reflow-Kontext + Überhang-Erkennung), `operations.py` (typisierte Plan-Operationen + atomarer Executor). Schüler-Kontext: `student_context.py` (aktuelles Thema, Klassenarbeits-Scope, Whitelist) |
| `calendar/` | Stundenplan-Anbindung (UP-8): Adapter-Interface (`base.py`) + WebUntis-Implementierung, Ferien-Übernahme, Wochenmuster-Ableitung, Abgleich von Entfall/Vertretung/Verlegung (`sync.py`: `plan_sync` rein, `apply_sync` schreibend). Wie bei `auth/` ist das Interface der Erweiterungspunkt für andere Quellen |
| `budget/` | Wochenmodell: Stufen aus YAML (`tiers.py`), Unterrichtswochen aus `school_year.yaml` (`schulwochen.py`), Zuteilungslogik (`accrual.py`), Hochrechnung (`forecast.py`), Wechselkurs (`exchange.py`) |
| `litellm/` | LiteLLM-HTTP-Client, Team-Anlage, User-Budget-Sync |
| `upload/` | Dateiupload-Session, Text-Extraktion (PDF via pdfminer.six, Bilder via Base64) |
| `db/` | SQLAlchemy-Modelle (async), Session-Factory |
| `api/admin/` | Admin-only-Endpunkte: Modell-Allowlists, Assistenten, Statistiken, Site-Texte |
| `api/assistants.py` | Öffentlicher Assistenten-Endpunkt (Sichtbarkeit nach Rolle) |
| `crons/` | Cron-Logik (Cleanup Accounts/Konversationen, Embedding-Backfill, Stundenplan-Abgleich) — wird von Skripten aufgerufen |
| `site_texts/` | Öffentliche Texte (Impressum, Datenschutz, Nutzungsregeln) aus DB |
| `preferences/` | Nutzerpräferenzen (Theme, Kostenanzeige-Granularität) |
| `config.py` | Pydantic-Settings — liest alle Umgebungsvariablen |
| `main.py` | FastAPI-App-Instanz, Router-Einbindung, CORS |

## Privacy-Invariante

**Personenbezogene Daten verlassen den Schulserver nie.**

Das ist die wichtigste architektonische Regel des Projekts. Konkret:

- `display_name` wird vom Auth-Adapter nur für die UI zurückgegeben und
  ausschließlich im `sessionStorage` des Browsers gehalten — **er wird
  niemals in die Datenbank geschrieben**.
- `external_id` (die Nutzer-ID vom SSO-Provider) wird **niemals** in LiteLLM,
  an KI-Anbieter oder in Chat-Inhalte übertragen.
- Alle Datenbankeinträge, LiteLLM-Anfragen und Kosten-Logs verwenden
  ausschließlich das `pseudonym` (HMAC-SHA256 aus `external_id` + `SCHOOL_SECRET`).

Eine Verletzung dieser Invariante ist ein kritischer Datenschutz-Bug.

## Datenmodell (wichtigste Tabellen)

| Tabelle | Primärschlüssel | Enthält |
|---------|----------------|---------|
| `users` | `pseudonym` (str) | Rolle, Jahrgang, letzter Login |
| `conversations` | UUID | `pseudonym`, Modell, Assistent-Ref, Titel, Kostensum |
| `messages` | UUID | `conversation_id`, Rolle, Inhalt (Text/JSON), Kosten |
| `assistants` | int | Name, System-Prompt, Modell, Status, Audience, Scope |
| `exchange_rates` | id | EUR→USD-Kurs, Quelle, Datum |
| `jwt_revocations` | `jti` | Revozierte Token-IDs |
| `pseudonym_audit` | `pseudonym` | De-Anonymisierungs-Log, Massen-Revokations-Zeitstempel |
| `site_texts` | `key` | Verwaltete Texte (impressum, datenschutz, regeln) |
