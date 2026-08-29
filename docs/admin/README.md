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

- [ ] [Vorüberlegungen](vor-der-installation.md) klären — vor allem die **Modellwahl**:
      Die Vektorbreite des Embedding-Modells lässt sich später nur mit Schemaänderung und
      vollständigem Re-Embedding korrigieren.
- [ ] Systemvoraussetzungen prüfen (Docker ≥ 24, Docker Compose ≥ 2.20)
- [ ] Repository klonen
- [ ] `.env` aus `.env.example` erstellen und befüllen
- [ ] **Alle** `config/*.yaml` aus ihren `.example`-Fassungen erstellen — es gibt keinen
      Rückfall auf die Beispieldatei ([Installation, Schritt 2](installation.md#schritt-2-konfiguration-anlegen))
- [ ] `infra/litellm_config.yaml` erstellen und die **`model_list` befüllen** — fertige
      Blöcke je Anbieter in [Modell-Szenarien](modell-szenarien.md)
- [ ] Modellnamen und Anbieter-Schlüssel in die `.env` eintragen (`CHAT_DEFAULT_MODEL`,
      `TITLE_MODEL`, `EMBEDDING_MODEL`) — Aufgabennamen, keine Produktnamen
- [ ] `docker compose up -d` ausführen
- [ ] Datenbank-Migration: `docker compose exec backend alembic upgrade head`
- [ ] Fächer einspielen: `docker compose exec backend python scripts/seed_subjects.py`
- [ ] Wechselkurs setzen: `docker compose exec backend python scripts/seed_exchange_rate.py --rate …`
- [ ] LiteLLM-Teams anlegen: `docker compose exec backend python scripts/create_litellm_teams.py`
- [ ] Konfiguration prüfen: `docker compose exec backend python scripts/check_litellm_config.py`
- [ ] Als Admin einloggen
- [ ] Modell-Freischaltungsmatrix unter `/settings/models` befüllen — **inklusive
      `TITLE_MODEL` in jeder Gruppe**
- [ ] Texte (Impressum, Datenschutz, Nutzungsregeln) unter `/settings/texts` hinterlegen
- [ ] Reverse Proxy einrichten und HTTPS aktivieren

---

## Inhaltsverzeichnis

- [Vor der Installation](vor-der-installation.md) — Schulspezifische Vorüberlegungen; bisher: Modellwahl mit Messwerten und Empfehlungen
- [Installation](installation.md) — Docker Compose, Reverse Proxy, Ersteinrichtung
- [Modell-Szenarien](modell-szenarien.md) — Vollständige Konfigurationen je Anbieter (IONOS, Mistral, OpenAI, Anthropic, Mischbetrieb) und die anbieterspezifischen Fallen
- [Konfigurationsdateien](konfiguration.md) — Alle Konfigurationsdateien im Detail
- [Nutzerverwaltung & Rollen](nutzerverwaltung.md) — SSO, Gruppen, Rollen, Jahrgänge
- [Budget-System](budget.md) — Tiers, ECB-Rate, Admin-UI
- [Modelle & Assistenten](modelle-und-assistenten.md) — Modelle freischalten, Assistenten verwalten
- [Embedding-Modell wechseln](../runbooks/modellwechsel.md) — Runbook: Schema angleichen + Re-Embedding
- [Bildungsplan-Import](bildungsplan-import.md) — Fachkontext in das Docker-Produktivsystem importieren
- [Curricula übertragen](../runbooks/curriculum-transfer.md) — Runbook: Schulcurricula exportieren und in promptLab/Dev einspielen
- [Stundenplan-Integration](stundenplan-integration.md) — WebUntis: Servicekonto, Fachkürzel, Ferien-Import, Abgleich-Cron
- [Datenschutz & Betrieb](datenschutz-betrieb.md) — Pseudonymisierung, Crons, Löschfristen
- [Updates & Wartung](updates-und-wartung.md) — Updates, Speicherplatz freigeben, Schuljahreswechsel, Troubleshooting
- [Content-Moderation & Guardrails](content-moderation.md) — Schulweiter Guardrail-Prompt, LiteLLM-Guardrails konfigurieren
- [Server-Rendering-Sidecar](server-rendering.md) — CircuiTikZ/Plots/PDF-Mathe: Betrieb, Config, Cache-Cleanup
- [Artefaktbibliothek](artefaktbibliothek.md) — Aufbewahrung/Quota, Ablage-Volume, Cleanup-Cron
- [Material-Werkstatt](material-werkstatt.md) — Pandoc-Abhängigkeit, Export-Vorlagen (CSS/reference-doc)
