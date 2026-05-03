# Entwickler-Dokumentation

Diese Dokumentation richtet sich an Entwickler:innen, die am Projekt
weiterarbeiten, es forken oder neue Adapter implementieren wollen.

**Voraussetzungen:** Python 3.10+, Node.js 20+, Grundkenntnisse in FastAPI
und Svelte. Docker ist für den Betrieb, aber nicht zwingend für die lokale
Entwicklung erforderlich.

---

## Repo-Struktur

```
backend/
├── app/                FastAPI-Anwendung (Module → siehe Architektur)
├── alembic/            Datenbank-Migrationen
├── scripts/            Wartungs- und Setup-Skripte
└── tests/              Unittests (tests/unit/) und Integrationstests

frontend/
├── src/
│   ├── lib/            Gemeinsame Hilfsmittel (api.js, stores/, components/)
│   └── routes/         SvelteKit-Routen ((app)/, (admin)/, info/)
└── vite.config.js

config/                 Laufzeitkonfiguration (.env, auth.yaml, budget_tiers.yaml)
infra/                  nginx, LiteLLM-Konfiguration, Caddy
docs/
├── user/               Anwender-Dokumentation
├── admin/              Admin-Dokumentation
└── dev/                Diese Dokumentation
Plaene/                 Planungsdokumente (nicht produktionsrelevant)
```

## Quick Start

Für die vollständige Anleitung zur lokalen Entwicklungsumgebung
→ [dev-setup.md](dev-setup.md)

Kurzversion:
```bash
# Backend
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp config/.env.example config/.env  # befüllen
alembic upgrade head
uvicorn app.main:app --reload

# Frontend (separates Terminal)
cd frontend && npm install && npm run dev
```

---

## Inhaltsverzeichnis

- [Systemarchitektur](architektur.md) — Komponenten, Datenfluss, Privacy-Invariante
- [Auth-Flow & Pseudonymisierung](auth-flow.md) — Adapter-Interface, JWT, Pseudonymisierung
- [Chat & Streaming](chat-streaming.md) — Chat-Request → LiteLLM → SSE-Antwort
- [Lokales Dev-Setup](dev-setup.md) — Entwicklungsumgebung ohne Docker
- [Backend-Entwicklung](backend-entwicklung.md) — Migrationen, Tests, Skripte
- [Neuen Auth-Adapter implementieren](neuer-auth-adapter.md) — AuthAdapter-Interface
- [Frontend-Konventionen](frontend-konventionen.md) — CSS-Tokens, Svelte 5, Routing
