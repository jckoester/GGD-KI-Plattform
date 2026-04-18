# Phase 1 — Implementierungsplan

## Übersicht

| Schritt | Thema | Ergebnis |
|---------|-------|----------|
| 0 | DB-Schema | Datenbankschema steht, Alembic eingerichtet |
| 1 | Authentifizierung | Login mit Test-Adapter + IServ, JWT, Pseudonymisierung, UI |
| 2 | Chat Basis | Streaming-Chat, Conversation + Messages persistiert |
| 3 | Chat Features | Budgets, Kostentransparenz, Crons |
| 4 | Admin + Statistik | Dashboard, Nutzungsstatistiken |
| 5 | Deployment | Docker Compose, nginx, Test-Deployment auf HomeLab |

## Vorgehen je Schritt

Plan besprechen → implementieren → testen → nächster Schritt.

## Notizen

- Entwicklung läuft lokal (kein Docker Compose), LiteLLM im lokalen Netz
- Docker Compose erst ab Schritt 5 relevant
- Test-Adapter (YAML-basiert) wird in Schritt 1 parallel zum IServ-Adapter gebaut, damit der gesamte weitere Dev-Prozess ohne IServ-Zugang testbar bleibt
