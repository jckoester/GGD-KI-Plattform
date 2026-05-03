# Admin-Dokumentation

Diese Dokumentation richtet sich an IT-Verantwortliche, die ki@schule installieren,
konfigurieren und betreiben. Vorausgesetzt werden Grundkenntnisse in Linux und
Docker Compose; Python- oder JavaScript-Kenntnisse sind nicht erforderlich.

---

## Architektur auf einen Blick

```
Browser
  └─▶ nginx (Reverse Proxy / TLS-Terminierung)
        ├─▶ Frontend  (SvelteKit, statisch gebaut)
        └─▶ Backend   (FastAPI)
              ├─▶ PostgreSQL   (Nutzer, Konversationen, Budgets)
              └─▶ LiteLLM      (KI-Proxy, Budgetdurchsetzung)
                    └─▶ KI-Anbieter  (OpenAI, Anthropic, Ollama, …)
```

Der **Cron-Container** läuft parallel und führt automatische Aufräumjobs sowie
die monatliche Budgeterneuerung aus.

Die **Pseudonymisierung** findet im Backend statt: Externe KI-Anbieter erhalten
ausschließlich anonyme Nutzer-IDs — nie Namen oder andere personenbezogene Daten.

---

## Schnellstart-Checkliste

Für eine vollständige Neuinstallation diese Schritte der Reihe nach durchführen:

- [ ] Systemvoraussetzungen prüfen (Docker ≥ 24, Docker Compose ≥ 2.20)
- [ ] Repository klonen
- [ ] `config/.env` aus `config/.env.example` erstellen und befüllen
- [ ] `config/auth.yaml` aus `config/auth.example.yaml` erstellen und befüllen
- [ ] `config/budget_tiers.yaml` aus `config/budget_tiers.example.yaml` erstellen
- [ ] `infra/litellm_config.yaml` aus `infra/litellm_config.example.yaml` erstellen
- [ ] `docker compose up -d` ausführen
- [ ] Datenbank-Migration: `docker compose exec backend alembic upgrade head`
- [ ] LiteLLM-Teams anlegen: `docker compose exec backend python scripts/create_litellm_teams.py`
- [ ] Als Admin einloggen
- [ ] Modell-Freischaltungsmatrix unter `/settings/models` befüllen
- [ ] Texte (Impressum, Datenschutz, Nutzungsregeln) unter `/settings/texts` hinterlegen
- [ ] Reverse Proxy einrichten und HTTPS aktivieren

---

## Inhaltsverzeichnis

- [Installation](installation.md) — Docker Compose, Reverse Proxy, Ersteinrichtung
- [Konfigurationsdateien](konfiguration.md) — Alle Konfigurationsdateien im Detail
- [Nutzerverwaltung & Rollen](nutzerverwaltung.md) — SSO, Gruppen, Rollen, Jahrgänge
- [Budget-System](budget.md) — Tiers, ECB-Rate, Admin-UI
- [Modelle & Assistenten](modelle-und-assistenten.md) — Modelle freischalten, Assistenten verwalten
- [Datenschutz & Betrieb](datenschutz-betrieb.md) — Pseudonymisierung, Crons, Löschfristen
- [Updates & Wartung](updates-und-wartung.md) — Updates, Schuljahreswechsel, Troubleshooting
