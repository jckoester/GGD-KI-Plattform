# Systemarchitektur

## Komponenten-Übersicht

```
Browser
  └─▶ nginx (Port 80, TLS-Terminierung extern via Caddy o. ä.)
        ├─▶ /          → Frontend (SvelteKit, Node)
        └─▶ /api/      → Backend (FastAPI, uvicorn)
                              ├─▶ PostgreSQL  (Nutzer, Konversationen, Budgets)
                              └─▶ LiteLLM     (KI-Proxy, Budget-Enforcement)
                                    └─▶ KI-Anbieter  (OpenAI, Anthropic, Ollama, …)

Cron-Container (separat):
  cleanup_inactive_accounts     täglich 02:00
  cleanup_stale_conversations   täglich 02:30
  refresh_ecb_rate              1. des Monats 06:00
  monthly_budget_reconcile      1. des Monats 07:00
```

## Backend-Module (`backend/app/`)

| Modul | Zweck |
|-------|-------|
| `auth/` | OAuth2/OIDC-Flow, JWT-Ausgabe und -Prüfung, Pseudonymisierung, Adapter-Interface |
| `chat/` | Chat-Endpunkte, SSE-Streaming, Konversations- und Nachrichtenverwaltung |
| `budget/` | Budget-Tiers aus YAML, ECB-Wechselkurs, Reconcile-Service |
| `litellm/` | LiteLLM-HTTP-Client, Team-Anlage, User-Budget-Sync |
| `upload/` | Dateiupload-Session, Text-Extraktion (PDF via pdfminer.six, Bilder via Base64) |
| `db/` | SQLAlchemy-Modelle (async), Session-Factory |
| `api/admin/` | Admin-only-Endpunkte: Modell-Allowlists, Assistenten, Statistiken, Site-Texte |
| `api/assistants.py` | Öffentlicher Assistenten-Endpunkt (Sichtbarkeit nach Rolle) |
| `crons/` | Cleanup-Logik (Accounts, Konversationen) — wird von Skripten aufgerufen |
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
