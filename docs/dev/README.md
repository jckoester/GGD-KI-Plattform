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
cp .env.example .env  # befüllen
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
- [Kontextsuche](kontextsuche.md) — Suchschicht, Stellschrauben fürs Feintuning, Prüfsatz
- [Fachbegriffe einspielen](fachbegriffe-import.md) — Schnittstelle des Seed-Skripts, Idempotenz, Bericht
- [Planung: Archiv, Rechte, Kopieren](planung-archiv-kopieren.md) — wer lesen und ändern darf, Archiv, was eine Kopie mitnimmt
- [Jahresverlaufsplan](jahresverlaufsplan.md) — Knotentyp `verlaufsplan`, eigener Schreibweg, Zeitrechnung, Kalender je Schuljahr, Übernehmen, Puffer (seit 0.59)
- [Vernetzung der Fächer](vernetzung.md) — Übersicht Fach × Fach je Stufe (seit 0.67) und Zeitachse über die Stufen: Dienst, Fassung je Stufe und Schuljahr, Schätzung, Bezüge, Anordnung, PDF, Testwelt (seit 0.66)
- [Begriffsvorschlag](begriffsvorschlag.md) — Begriffe aus den Phasentexten: Ablauf, Fallen, Konfiguration
- [Begriffe im Curriculum](curriculum-begriffe.md) — Begriffe und Fachmethoden am Eintrag: Format, Abgleich, Auflösung, Gerüste, Planung
- [Entwürfe von Curricula](curriculum-entwurf.md) — Status `draft`, eine Rechteregel mit Fachvorsitz, Veröffentlichen und Ersetzen, Abdeckung; seit 0.46 kommende Fassung, Rückgängig, Rahmen, Funktionen des Curriculum-Assistenten, Bänder des Bildungsplans und Abdeckung über Band und Fassung
- [Leitlinien der Schule](leitlinien.md) — `leitbild` und `leitbild_aspekt`, Kürzel statt Kanten, Token `lb`/`lba` im Curriculum, Felder des Curriculum-Assistenten (seit 0.50); schulweite Übersicht je Leitlinie und Leitperspektive (seit 0.53)
- [MCP-Server für KI-Abos](mcp.md) — Aufbau, Schutzschichten, neun lesende Werkzeuge, OAuth-Autorisierungsserver (seit 0.55), Wächter, Tests (seit 0.54)
- [Curriculum aus YAML importieren](curriculum-yaml-import.md) — Format, Bereinigung und Grenzen, Entwurfsmodus des Imports, Vorschau im Savepoint, Endpunkte, MCP-Prüfung (seit 0.56)
- [Neuen Knotentyp einführen](neuer-knotentyp.md) — Checkliste, Netzwerkgraph, die vier stummen Fallen
- [Bildgenerierung](bildgenerierung.md) — Chat-Tool, Persistenz/Lifecycle, Moderations-Schichten
- [Server-Rendering](server-rendering.md) — CircuiTikZ/Plots/PDF-Mathe: Sidecar, Render-Router, Cache
- [Artefaktbibliothek](artefaktbibliothek.md) — `artifacts`-Modell, Promotion/Idempotenz, ggb-Export
- [Werkstatt: Dokumente](material-werkstatt.md) — Dokument-Editor, Export-Pfade (weasyprint/Pandoc), Dialekt-Parität
- [Schüler-Assistenten messen und ausliefern](assistenten-messen.md) — Szenarien, Messskript, Seed, Auslöser-Beispiele, Vorschlagsmessung
- [Hinweise auf Neuerungen](neuigkeiten.md) — Hinweise auf der Startseite schreiben, wer sie sieht
- [Einrichtung beim ersten Login](einrichtung.md) — wann der Dialog aufgeht, was er speichert, wie eine Seite dazukommt; seit 0.47 auch für Schüler:innen (Stichtag je Rolle, Vorschau)
- [Lokales Dev-Setup](dev-setup.md) — Entwicklungsumgebung ohne Docker
- [Backend-Entwicklung](backend-entwicklung.md) — Migrationen, Tests, Skripte
- [Vorschaumodus](vorschau.md) — Token mit Schülerrolle, Mitgliedschaften, Schreibsperre, Vorschau-Chats; was eine neue Route beachten muss
- [Audit-Log](audit-log.md) — Audit-Log oder Logger, Ereignisse schreiben, was nie hineingehört, nur anhängen
- [Neuen Auth-Adapter implementieren](neuer-auth-adapter.md) — AuthAdapter-Interface
- [Frontend-Konventionen](frontend-konventionen.md) — CSS-Tokens, Svelte 5, Routing; seit 0.48 zwei Seitenbreiten, Zurück und Rückweg `?back=`, Pfade der Verwaltung
