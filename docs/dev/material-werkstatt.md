# Material-Werkstatt (Phase 19)

Nutzereditierbare Markdown-Dokumente + Export nach PDF/DOCX/ODT. Baut auf der
[Artefaktbibliothek](artefaktbibliothek.md) auf. Code in `backend/app/export/` +
`frontend/src/routes/(app)/library/[id]/edit`.

## Dokument-Artefakt

`artifacts.kind='document'`, `mime_type='text/markdown'`, Quelle = `source` (die Datei-Bytes sind
dieselbe Markdown-Quelle). **Mutabel** — anders als Bilder/Diagramme trägt ein Dokument **kein**
`origin_ref` (nicht content-adressiert). `store.create_document` / `update_document`; Update prüft
die Quota unter Abzug der alten Größe und **erneuert `expires_at`** (aktiv bearbeitete Dokumente
laufen nicht ab). Endpunkte: `POST /artifacts/document`, `PUT /artifacts/{id}` (nur `document`),
`GET /artifacts/{id}/document`.

## Zwei Export-Pfade (bewusst getrennt)

| Format | Pfad | Warum |
|--------|------|-------|
| **PDF** | `render.export.render_markdown_for_pdf` (markdown-it-py) → Jinja-Template `export/templates/document_pdf.html` → weasyprint | maximale Vorschau-Parität; Mathe/Diagramme schon als SVG prärendert (Phase 17) |
| **DOCX/ODT** | `export.prerender.prerender_diagrams` → `export.pandoc.markdown_to_office` | Pandoc → **OMML** (echte Word-Formeln); `--reference-doc` als Vorlage |

`export.document.export_document(db, *, markdown, title, fmt, reference_doc, extra_css)` bündelt
beides. Endpunkt `POST /artifacts/{id}/export?format=&save=` (`save=false` Download, `save=true`
→ `export_*`-Artefakt).

### Sicherheit (nutzereditierbarer Inhalt)

- Pandoc: **`--sandbox`** (kein Datei-/Netzzugriff), Reader ohne `raw_tex`, Timeout + Größenlimit.
- Diagramme werden als **Bild-Daten-URI** eingebettet — lokale Bilddateien würde `--sandbox`
  ohnehin blocken. Prärender: `circuit`/`plot` → SVG (Render-Pipeline), `mermaid` bleibt v1
  Codeblock, Mathe konvertiert Pandoc selbst.

## Dialekt-Parität (Vorschau vs. Export)

Drei Renderer: Editor-/Chat-**Vorschau** = `marked` (GFM); **PDF** = markdown-it-py; **DOCX/ODT**
= Pandoc `commonmark_x+hard_line_breaks`. Angeglichen: Überschriften, Fett/Kursiv, Listen,
**Tabellen**, **Strikethrough**, **harte Zeilenumbrüche**, Code, Zitate, Mathe. Bewusst
verbleibende Abweichungen (Tests: `test_export_parity.py`):

- **Fußnoten** (`[^1]`): Export ✔ (echte Fußnote), Vorschau ✘ (`marked` ohne Footnote-Plugin →
  Rohtext). → Todo: Footnote-Plugin in `marked`.
- **Task-Listen** (`- [ ]`): Vorschau = Checkbox, beide Exporte = `[ ]`/`[x]`-Text.

## Vorlagen-Governance (Schritt 6)

`export.templates`: PDF-**CSS** in `site_config` (`export_css`) → `extra_css` im Template;
DOCX/ODT-**reference-doc** auf Disk (`EXPORT_TEMPLATE_DIR`, cwd-unabhängig). Admin-Router
`app/api/admin/export_templates.py` (`require_role("admin")`). Fehlt eine Vorlage → Default-Optik.

## Frontend

`lib/api.js` (`createDocument`/`getDocument`/`updateDocument`, `getDocumentExportBlob`/
`saveDocumentExport`, Admin-Vorlagen-Funktionen) · `lib/workshop.js` `deriveDocTitle` ·
Editor-Route `(app)/library/[id]/edit` (Textarea ⇄ Vorschau via `renderMarkdown` +
`renderDiagrams` + `renderServerBlocks`, Export-Leiste) · Admin-Seite `(admin)/settings/export`.
Einstieg aus dem Chat: `MessageBubble` „In Werkstatt öffnen".
