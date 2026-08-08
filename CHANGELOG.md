# Changelog

Alle nennenswerten Änderungen an der GGD-KI-Plattform. Versionierung nach
[Semantic Versioning](https://semver.org/lang/de/) (0.x = vor dem ersten Stable-Release).

## [Unreleased]

## [0.4.0] – 2026-08-08

Zwei Schwerpunkte: die Plattform wird **anbieterunabhängig** — kein Modellname steht mehr
im Code, ein Wechsel ist Konfigurationsarbeit — und sie liest erstmals den **Stundenplan**,
sodass Wochenmuster, Ferien und Vertretungsplan nicht länger von Hand in die
Unterrichtsplanung übertragen werden müssen.

Dazu kommen die zuvor auf einem eigenen Zweig entwickelten Modalitäten: **Bildgenerierung**,
**Server-Rendering** (Schaltpläne, Funktionsgraphen, Mathematik in PDFs), die
**Artefaktbibliothek** und die **Material-Werkstatt** mit Export nach PDF, Word und ODT.

### Neu

**Stundenplan-Integration (WebUntis)**
- **Wochenmuster aus dem Stundenplan übernehmen** statt eintippen — inklusive Doppelstunden
  (erkannt am lückenlosen Zeitraster, nicht geraten) und 14-tägigem Rhythmus. Der Vorschlag
  füllt den vorhandenen Editor; gespeichert wird erst nach Prüfung durch die Lehrkraft.
- **Ferien, Feiertage und bewegliche Ferientage** einmal je Schuljahr übernehmen
  (`/settings/holidays`). Der Vorschlag **ergänzt** die vorhandene Konfiguration, statt sie
  zu ersetzen — beide Seiten kennen Tage, die die andere nicht hat.
- **Entfall, Vertretung und Verlegung** fließen in die Jahresplanung: als Cron werktags um
  5:30 Uhr und als Handabgleich im Jahresplan und im Profil. Der Handabgleich ist der
  Hauptweg — Vertretungspläne werden vielerorts erst Minuten vor Unterrichtsbeginn gepflegt.
- **Vertretung gilt nicht als gehaltene Stunde.** Die vertretende Lehrkraft beaufsichtigt;
  das geplante Stundenziel bleibt offen, der Slot wird zum Anpassen vorgemerkt.
- **Verlegungen erscheinen als Vorschlag**, nicht als Änderung, und öffnen den vorhandenen
  Verschiebe-Assistenten. Ein Paar (Ursprung + Ziel) ergibt eine Meldung, eine verlegte
  Doppelstunde ebenfalls.
- Adapter-Schnittstelle wie beim Auth-Adapter: WebUntis ist die erste Quelle, nicht die
  einzig mögliche. **Ohne `WEBUNTIS_SERVER` bleibt die Integration unsichtbar** — die
  Unterrichtsplanung funktioniert unverändert mit Handpflege.
- Dokumentation: [Stundenplan-Integration](docs/admin/stundenplan-integration.md) (Admin),
  [Stundenplan übernehmen](docs/user/stundenplan.md) (Lehrkräfte), Eintrag fürs
  Verarbeitungsverzeichnis in [Datenschutz & Betrieb](docs/admin/datenschutz-betrieb.md).

**Bildgenerierung**
- Bild-Werkzeug im Chat mit eigener Modell-Freischaltungsmatrix, Kostenerfassung und
  Anzeige im Verlauf.
- **Jugendschutz-Prüfpunkt:** Ein schulweiter, schülersichtbarer Bild-Assistent geht nicht
  ohne ausdrückliche Freigabe live. Mehrschichtige Moderation mit fail-closed Blockliste.
- Werkzeugübersicht unter `/tools`; Aufräum-Cron für erzeugte Bilder.

**Server-Rendering**
- **Schaltpläne (CircuiTikZ)** und **Funktionsgraphen** werden serverseitig als SVG
  gerendert und im Chat sowie im Wissensgraph angezeigt. Plot-Ausdrücke werden über eine
  Whitelist geparst und ohne `eval` ausgewertet.
- **Mathematik in PDF-Exporten** (MathJax-SVG) — im Browser rendert KaTeX, das aber kein
  SVG erzeugt und daher für Exporte nicht taugt.
- Eigener Sidecar-Dienst (`render-sidecar/`), Ergebnis-Cache, Aufräum-Cron.

**Artefaktbibliothek**
- Bilder, Diagramme, Schaltpläne und Graphen aus dem Chat dauerhaft speichern
  (`/library`), herunterladen, als PNG oder Quelltext exportieren.
- **GeoGebra-Export** für Funktionsgraphen (`.ggb`).
- Aufbewahrungsfrist je Artefakt, Aufräum-Cron, gemeinsames Ablage-Volume.

**Material-Werkstatt**
- Markdown-Dokumente aus dem Chat in einen Editor übernehmen („In Werkstatt öffnen"),
  bearbeiten und mit Live-Vorschau prüfen.
- **Export nach PDF, Word (DOCX) und ODT** — Mathematik wird zu OMML, Diagramme werden
  vorgerendert eingebettet.
- **Schulweite Vorlagen** für Layout und Schrift (`/settings/export`).

**Anbieterwechsel vorbereitet**
- **Kein Modellname mehr im Code.** Chat-, Titel-, Embedding- und Bildmodell kommen
  vollständig aus der `.env`; die Werte sind die Namen aus der LiteLLM-Config, nicht die
  Produkt-IDs der Anbieter. Ein Anbieterwechsel bleibt damit auf die Proxy-Config beschränkt.
- **Assistenten müssen kein Modell mehr festlegen.** Ohne Angabe gilt das Standardmodell —
  vorher machte ein fest eingetragenes Modell einen Assistenten bei jedem Setup-Wechsel
  unbrauchbar.
- **Warnung bei verschwundenen Modellen:** Verweist ein Assistent auf ein Modell, das der
  Proxy nicht mehr führt, meldet das die Assistenten-Verwaltung, statt es beim ersten
  Chat scheitern zu lassen.
- **Modellwähler-Filter** (`MODEL_PICKER_HIDDEN_PREFIXES`): interne Modelle (Titel,
  Moderation) und andere Modalitäten verschwinden aus dem Dropdown. Rein kosmetisch,
  Freigaben bleiben unberührt.
- **Bildgenerierung modellunabhängig:** Formate über `IMAGE_SIZES` konfigurierbar,
  `IMAGE_RESPONSE_FORMAT` für Modelle, die Base64 statt URLs liefern.
- **Moderation ohne OpenAI-Zugang:** LLM-gestützter Guardrail als Ersatz für die
  OpenAI-Moderation-API, die nicht jeder Anbieter hat.
- `backend/scripts/check_litellm_config.py` prüft die Proxy-Konfiguration vor der
  Inbetriebnahme; Vorlage `infra/litellm_config.ionos.example.yaml` für einen EU-Anbieter.

**Werkzeuge und Dokumentation**
- [Runbook: Embedding-Modell wechseln](docs/runbooks/modellwechsel.md) — Schema angleichen,
  Re-Embedding, Verifikation, Rollback.
- `backend/scripts/resize_embedding_column.py` für den Wechsel der Vektorbreite im
  laufenden Betrieb.
- ESLint im Frontend erstmals einsatzfähig — `npm run lint` lief vorher ins Leere.

### Geändert
- **Embedding-Modell ist konfigurierbar.** Modellname, Vektorbreite, Input-Cap und der
  optionale `dimensions`-Parameter kommen aus der `.env` (`EMBEDDING_MODEL`,
  `EMBEDDING_DIMENSIONS`, `EMBEDDING_MAX_CHARS`, `EMBEDDING_SEND_DIMENSIONS`) statt aus
  Literalen im Code. Die Defaults entsprechen dem bisherigen Stand
  (`text-embedding-3-small`, 1536) — **bestehende Installationen brauchen keine Änderung.**
- Passt die Vektorbreite des Modells nicht zur Konfiguration, bricht die Embedding-Generierung
  mit einer `EmbeddingDimensionError` ab, die beide Breiten und den Modellnamen nennt (vorher:
  unverständlicher pgvector-Fehler beim Schreiben). Ein Startup-Check meldet die Abweichung
  schon beim Hochfahren.
- Die **Kontolöschung nach 90 Tagen** räumt zusätzlich den Stundenplan-Abrufstatus ab. Ein
  Strukturtest verlangt für jede neue Tabelle mit Pseudonym-Spalte eine ausdrückliche
  Entscheidung — die Lücke war zuvor nur zufällig aufgefallen.
- `alembic revision --autogenerate` erzeugt wieder brauchbare Migrationen: 21 Altlasten
  zwischen Modellen und Schema beseitigt (fehlende `Text`-Typen und Indizes in
  `app/db/models.py`, Migration `0042` für zwei DB-seitige Abweichungen). Vorher hätte
  `--autogenerate` eine Migration erzeugt, die sechs Indizes löscht.
- `pytest tests/` läuft wieder vollständig durch: `alembic/env.py` deaktivierte über
  `fileConfig` sämtliche `app.*`-Logger, wodurch ein Test im kombinierten Lauf fehlschlug.

### Behoben
- **Wochenmuster: einmalige Klassenarbeiten verfälschten das Muster.** Reichte eine Klausur
  in die Folgestunde, verschmolz die davorliegende **wöchentliche** Stunde mit ihr zu einer
  „Doppelstunde, 1× gesehen" — falsche Länge und verlorene Sicherheit. Verschmolzen wird
  jetzt nur noch, wenn die Stunden auch tatsächlich gemeinsam auftraten. Gefunden bei der
  Abnahme gegen die Pläne aller 90 Lehrkräfte.
- Bildungsplan-Import: fehlende Abhängigkeit `bs4` im Container, LFDB-Import im Runbook.

### Migration
- `alembic upgrade head` einspielen (`0038`–`0046`).
- `0043` ist **idempotent**: Bei unverändertem `EMBEDDING_DIMENSIONS` passiert nichts und
  vorhandene Embeddings bleiben erhalten. Nur wer die Breite ändert, braucht anschließend ein
  vollständiges Re-Embedding (`scripts/embedding_backfill.py`) — bis dahin liefert die
  semantische Suche keine Treffer. Ablauf im Runbook oben.
- `python scripts/seed_subjects.py` ausführen — die Fächer tragen jetzt die Fachkürzel des
  Stundenplans (`untis_codes`).
- **Optional:** Wer den Stundenplan anbinden möchte, ergänzt die `WEBUNTIS_*`-Zeilen in der
  `.env`. Ohne sie ändert sich für Nutzer:innen nichts.
- Neue Dienste in `docker-compose.yml`: Render-Sidecar sowie Cron-Einträge für
  Stundenplan-Abgleich und das Aufräumen von Bildern, Artefakten und Render-Cache.

## [0.3.0] – 2026-07-16

Schwerpunkte: Unterrichtsplanung, pädagogische und rechtliche Leitplanken
(Krisenerkennung, PII-Warnung, Jugendschutz), Bildungsplan-Editionen samt
PDF-Import (Fremdsprachen und Leitfaden Demokratiebildung) sowie ein
Sicherheits-Audit.

### Neu
- **Unterrichtsplanung:** Jahresplanung mit Planungs-Assistent, Stundenentwurf und
  Nachbereitung/Engagement; Methoden und Sozialformen als eigene Wissens-Knotentypen;
  Export (Markdown/PDF/DOCX).
- **Bildungsplan-Editionen:** editionsbewusste Versionierung (`bp_version`, `.V2`/`.V3`)
  mit jahrgangsweiser Frontier und Curriculum-Migration auf neue Editionen.
- **Operatoren:** handlungsleitende Verben (AFB I–III) als content_type `operator` –
  Scraper/Import, Darstellung im Bildungsplan, Chat-Werkzeug, Embeddings.
- **PDF-Bildungsplan-Import:** neue Pipeline `scripts/pdf_import/` für nur als PDF
  veröffentlichte Pläne – **Leitfaden Demokratiebildung (LFDB)** sowie die
  **Fremdsprachen (Englisch, Französisch)** inklusive Operatoren. LLM-gestützte
  Extraktion mit menschlicher Review, deterministische Assemblierung, dieselben
  Knotentypen wie der HTML-Scraper (keine UI-Sonderwege).
- **Krisenerkennung (ADR-008):** lokale Trigger-Erkennung parallel zum Chat,
  nicht-alarmierende Hilfe-Banner, pseudonyme Flags, Soft-Delete geflaggter Konversationen.
- **Krisen-Einsicht (4-Augen-Prinzip):** Rolle `review`, Flag-Dashboard,
  Step-up-Authentifizierung, Zweitfreigabe und protokollierte Reader-Ansicht.
- **Pädagogische Leitplanken:** zielgruppengerechte Präambeln, Lernverhalten-Augmentierungen
  und Jugendschutz-Prüfpunkte für Assistenten.
- **PII-Eingabewarnung:** Datensparsamkeit-Gate vor dem Senden (Server-NER + Client-Regex),
  fail-open, pro Konversation unterdrückbar.
- **Rich-Rendering:** KaTeX + mhchem (Mathematik/Chemie) und Mermaid-Diagramme in Chat,
  Wissensgraph, Curriculum und Hilfe.
- **Wissensgraph:** getrennte Lese- und Bearbeitungsansicht, Knoten-Aliase, paginierte Listen.

### Sicherheit
- **Sicherheits-Audit (18 Funde behoben):** PKCE und Browser-Bindung im OAuth-Login,
  ID-Token-Verifikation gegen JWKS, Rate-Limiting, Härtung der Step-up-Authentifizierung,
  4-Augen-Prinzip gegen Doppelrollen-Nutzer, Magic-Byte-Prüfung bei Uploads, explizite
  URL-Allowlist in DOMPurify, Erzwingen von Mindest-Secret-Längen, Upload-Limits,
  korrekte Kostenabrechnung der Titelgenerierung, Leserechte-Prüfung im Wissensgraph.

### Behoben
- Bildungsplan: fachweiser Fehlerabfang im Scraper, NWT-BF-Kursstufe, Reaktivierung
  zuvor archivierter Knoten, editierbare Knotentitel (Admin), Performance der
  Wissensgraph-Liste (Paginierung), Rollenwechsel ohne Neu-Login, u. a.

Ältere Versionen: siehe Git-Tags (`0.2.0`, `0.1.3`, `v0.1.2`, …).
