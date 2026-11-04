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
| `assistants/` | Wer darf welchen Assistenten benutzen (`sichtbarkeit.py`) — **eine** Regel in drei Darstellungen: `darf_nutzen()` für den einzelnen Fall (Chat), `sichtbar_klausel()` für die Liste und seit 0.32 `warum_nicht()` für den **Grund** eines Neins (Kennungen in `GRUENDE`, Texte in `frontend/src/lib/schuelersicht.js`). Ein Prüfsatz lässt alle drei am selben Bestand gegeneinander laufen; wer die Regel ändert, ändert alle drei. Bis 09/2026 gab es die Regel zweimal, und keine der beiden kannte die Scopes |
| `chat/` | Chat-Endpunkte, SSE-Streaming, Konversations- und Nachrichtenverwaltung, Tool-Registry (`tools.py`: `planning` / `student_planning`) |
| `context/` | Kontextspeicher: Knoten/Kanten, Curriculum-Import, Retrieval (semantisch + Engagement-UNION), Taxonomie |
| `planning/` | Unterrichtsplanung (UP-Reihe): Slots/Snapshots, Jahresplan- und Stundenentwurfs-Logik, Assistenten-Tools. Slot-Erzeugung: `slot_generator.py` (Neuaufbau verschont `source != 'pattern'`). Stundenrasterwechsel: `umhaengen.py` (`plane_umhaengen` rein / `wende_umhaengen_an` schreibend — Fixpunkte behalten ihr Datum, der Rest wandert nach Reihenfolge, Übriges auf den Parkplatz). Verschiebe-Dialog: `reflow_service.py` (Reflow-Kontext + Überhang-Erkennung), `operations.py` (typisierte Plan-Operationen + atomarer Executor). Schüler-Kontext: `student_context.py` (aktuelles Thema, Klassenarbeits-Scope, Whitelist). Startseite und „Jetzt"-Block: `mein_tag.py` (heutige und nächste Stunden je Rolle) und `jetzt.py` (wo stehe ich in der Einheit) — beide **reine Regeln ohne Datenbank**, damit sich die Grenzfälle des Kalenders (Freitag, Ferienvorabend, Schuljahresende) prüfen lassen, ohne eine Welt aufzubauen. ⚠️ `lesson_slots` trägt **keine Uhrzeit**, nur `start_period`/`periods`: Es gibt eine Reihenfolge, aber kein „vergangen" |
| `calendar/` | Stundenplan-Anbindung (UP-8): Adapter-Interface (`base.py`) + WebUntis-Implementierung, Ferien-Übernahme, Wochenmuster-Ableitung, Abgleich von Entfall/Vertretung/Verlegung (`sync.py`: `plan_sync` rein, `apply_sync` schreibend — legt fehlende Slots mit `source='import'` an, aber nur für Gruppen mit Planung). Wie bei `auth/` ist das Interface der Erweiterungspunkt für andere Quellen |
| `budget/` | Wochenmodell: Stufen aus YAML (`tiers.py`), Unterrichtswochen aus `school_year.yaml` (`schulwochen.py`), Zuteilungslogik (`accrual.py`), Hochrechnung (`forecast.py`), Wechselkurs (`exchange.py`) |
| `litellm/` | LiteLLM-HTTP-Client, Team-Anlage, User-Budget-Sync |
| `upload/` | Dateiupload-Session, Text-Extraktion (PDF via pdfminer.six, Bilder via Base64) |
| `db/` | SQLAlchemy-Modelle (async), Session-Factory |
| `api/admin/` | Admin-only-Endpunkte: Modell-Allowlists, Assistenten, Statistiken, Site-Texte, Rückmeldungen |
| `api/assistants.py` | Öffentlicher Assistenten-Endpunkt (Sichtbarkeit nach Rolle) |
| `crons/` | Cron-Logik (Cleanup Accounts/Konversationen/Rückmeldungen, Embedding-Backfill, Stundenplan-Abgleich) — wird von Skripten aufgerufen |
| `site_texts/` | Öffentliche Texte (Impressum, Datenschutz, Nutzungsregeln) aus DB |
| `preferences/` | Nutzerpräferenzen (Theme, Kostenanzeige-Granularität) |
| `groups/` | Unterrichtsgruppen jenseits der Endpunkte: Beitrittscodes (`beitritt.py` — reine Regeln plus schreibende Vorgänge, Rücknahme als Menge), die Aktualitätsregel „gehört zum laufenden Schuljahr?" (`aktualitaet.py`, geteilt mit dem Stundenplan-Abgleich) die Angebote für neue SSO-Unterrichtsgruppen (`angebote.py` — zuordnen, anlegen, ignorieren) und die Schülersicht auf die Assistenten einer Gruppe (`schuelersicht.py`, seit 0.32 — ein nachgebauter Schüler-`Zugang` für dieselbe Regel, keine eigene Auswahl) |
| `feedback/` | Rückmeldekanal (ADR-020): Endpunkte für alle Rollen, Statusmaschine und Missbrauchsschutz (`service.py` — von Nutzer- **und** Admin-Seite benutzt), Chat-Snapshot, Benachrichtigung mit Stundenfenster; seit 0.31 bekannte Probleme (`GET /feedback/public`) und die Antwortbewertung (`bewertung.py`: `PUT /messages/{id}/rating`, Wochenzähler `rating_counts` in derselben Transaktion) |
| `config.py` | Pydantic-Settings — liest alle Umgebungsvariablen |
| `main.py` | FastAPI-App-Instanz, Router-Einbindung, CORS |
| `api/` | Übrige Endpunkt-Module neben `api/admin/`: Gruppen, Fächer, Bildarten, Zugangstoken, Leitplanken, PII-Prüfung, Krisen-Freigabe (`review.py`), Archiv |
| `artifacts/` | Artefaktbibliothek (Phase 18): Speicher (`store.py`), Übernahme aus dem Chat (`promote.py`, `uebernahme.py`), GeoGebra-Export, Mengengrenzen |
| `core/` | Querschnitt ohne eigene Fachlichkeit: Client-IP, Hintergrundaufgaben, Pfade, Produktions-Selbstprüfung, Audit-Log schreiben (`audit.py`, [audit-log.md](audit-log.md)) |
| `crisis/` | Krisenerkennung (ADR-008): Schlüsselwort-Erkennung (`detector.py`), Benachrichtigung, Erinnerungen an unerledigte Fälle |
| `export/` | Ausgabeformate: PDF (weasyprint), DOCX/ODT (Pandoc), Vorlagen, Prärendern von Diagrammen |
| `mail/` | SMTP-Versand — einzige Stelle, die Mails verschickt |
| `models/` | Platzhalter-Paket ohne Inhalt; die SQLAlchemy-Modelle liegen in `db/` |
| `pedagogy/` | Pädagogische Leitplanken (ADR-008 Teil 1+2): `pedagogy.yaml` laden, Präambeln und Lernverhalten in den System-Prompt komponieren |
| `pii/` | Datensparsamkeit-Gate (Phase 14): lokale NER + Muster, ohne Netzaufruf |
| `ratelimit/` | Drosselung: Regeln aus `rate_limits.yaml`, Zähler, FastAPI-Abhängigkeit |
| `render/` | Server-Rendering (Phase 17): CircuiTikZ/MathJax über den Node-Sidecar, Plot-Auswertung, Cache |
| `ui/` | Darstellungsstufen: `ui_levels.yaml` laden und ausliefern — was die Oberfläche zeigt, nicht was sie darf |
| `neuigkeiten/` | Hinweise auf Neuerungen für die Startseite: `neuigkeiten.yaml` laden und prüfen, je Person filtern (Rolle, geschlossen, Kontoalter, Ablauf, Darstellungsstufe — eine Regel in `quelle.py`), schließen ([neuigkeiten.md](neuigkeiten.md)) |

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
| `pseudonym_audit` | `pseudonym` | Rolle(n), Jahrgang, letzter Login, Massen-Revokations-Zeitstempel. ⚠️ Eine Tabelle `users` gibt es nicht — hier stand sie bis zum 25.09.2026 |
| `conversations` | UUID | `pseudonym`, Modell, Assistent-Ref, Titel, Kostensum |
| `messages` | UUID | `conversation_id`, Rolle, Inhalt (Text/JSON), Kosten |
| `assistants` | int | Name, System-Prompt, Modell, Status, Audience, Scope |
| `exchange_rates` | id | EUR→USD-Kurs, Quelle, Datum |
| `jwt_revocations` | `jti` | Revozierte Token-IDs |
| `audit_log` | id | Sicherheitsrelevante Ereignisse: Kategorie, Ereignis, Akteur (Pseudonym, Rolle), Ziel, Angaben ohne Inhalte; nur anhängen ([audit-log.md](audit-log.md)) |
| `site_texts` | `key` | Verwaltete Texte (impressum, datenschutz, regeln) |
| `group_source_classes` | (group_id, class_group_id) | Aus welchen Klassen sich eine Unterrichtsgruppe speist — Herkunft, nicht Mitgliedschaft |
| `group_join_codes` | UUID | Beitrittscode je Gruppe: Code, Gültigkeit, Widerruf, ausgebendes Pseudonym |
| `sso_group_offers` | UUID | Neue SSO-Unterrichtsgruppe, die noch keiner Plattform-Gruppe zugeordnet ist — je Lehrkraft eine Zeile |
