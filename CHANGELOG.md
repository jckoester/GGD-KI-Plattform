# Changelog

Alle nennenswerten Änderungen an der GGD-KI-Plattform. Versionierung nach
[Semantic Versioning](https://semver.org/lang/de/) (0.x = vor dem ersten Stable-Release).

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
