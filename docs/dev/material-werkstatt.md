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
| **DOCX/ODT** | `export.prerender.prerender_diagrams` → `export.pandoc.markdown_to_office` (Markdown → JSON → DOCX/ODT) | Pandoc → **OMML** (echte Word-Formeln); `--reference-doc` als Vorlage (`export.templates.vorlage`) |

`export.document.export_document(db, *, markdown, title, fmt, reference_doc, extra_css)` bündelt
beides. Endpunkt `POST /artifacts/{id}/export?format=&save=` (`save=false` Download, `save=true`
→ `export_*`-Artefakt).

### Sicherheit (nutzereditierbarer Inhalt)

- Pandoc: **`--sandbox`** (kein Datei-/Netzzugriff), Reader ohne `raw_tex`, Timeout + Größenlimit.
- Diagramme werden als **Bild-Daten-URI** eingebettet — lokale Bilddateien würde `--sandbox`
  ohnehin blocken. Prärender: `circuit`/`plot`/`smiles`/`mermaid` → SVG (Render-Pipeline;
  Mermaid seit 0.36 über Pele im Sidecar), Mathe konvertiert Pandoc selbst.

## Dialekt-Parität (Vorschau vs. Export)

Drei Renderer: Editor-/Chat-**Vorschau** = `marked` (GFM); **PDF** = markdown-it-py; **DOCX/ODT**
= Pandoc `commonmark_x+hard_line_breaks`. Angeglichen: Überschriften, Fett/Kursiv, Listen,
**Tabellen**, **Strikethrough**, **harte Zeilenumbrüche**, Code, Zitate, Mathe und seit 0.12
**Fußnoten** (`[^1]`): Vorschau (`marked-footnote`) und PDF (`mdit_py_plugins.footnote`) setzen
sie als Anmerkungen ans Dokumentende, DOCX/ODT als echte Fußnoten unten auf der Seite.
⚠️ Bis 0.11 zeigte nicht nur die Vorschau, sondern auch das **PDF** Rohtext — der Paritätstest
prüfte Fußnoten nur für DOCX, und diese Seite nannte den Export pauschal „✔". Bewusst
verbleibende Abweichungen (Tests: `test_export_parity.py`):

- **Fußnoten-Anker** brauchen in der Vorschau eine Kennung je Ausgabe (`renderMarkdown`
  ersetzt den Platzhalter durch die Nonce) — im Chat stehen viele Antworten auf einer Seite.
- **Task-Listen** (`- [ ]`): Vorschau = Checkbox, beide Exporte = `[ ]`/`[x]`-Text.

### Zwei Fallen im Pandoc-Weg (0.39)

- ⚠️ **`\(…\)` und `\[…\]` kennt `commonmark_x` nicht** — nur `$…$`/`$$…$$`, und
  `tex_math_single_backslash` gibt es für diesen Leser nicht. Ohne Umschreibung frisst die
  Escape-Regel den Backslash: Aus `\[y\]` wurde im DOCX der Text „[y]“. Das traf jede abgesetzte
  Formel aus dem Chat (`pedagogy.yaml` lässt `\[…\]` schreiben). `pandoc.klammer_mathe_zu_dollar`
  schreibt sie vor Pandoc um, außerhalb von Code. Der PDF-Weg hat dafür `_klammer_mathe_regel`.
- ⚠️ **Rohes HTML verwirft der DOCX-Writer** — aus „a<br>b“ wurde „ab“. Deshalb läuft auch die
  Werkstatt seit 0.39 über das JSON-Dokument: `pandoc.roh_html_umsetzen` macht aus `<br>` einen
  Zeilenumbruch und aus `<sub>`/`<sup>` tief-/hochgestellten Text, jedes andere Tag fällt weg.
  Dieselbe Regel gilt im PDF (`render.export.EXPORT_TAGS`) und in der Werkstatt-Vorschau
  (`renderMarkdown(…, { wieImExport: true })`). Im Chat ändert sich nichts.

## Office-Export aus Bausteinen: Stundenentwurf und Curriculum (0.39)

Beide sind **Tabellen, in deren Zellen Markdown steht**. Eine Markdown-Pipe-Tabelle kann keine
Absätze oder Listen in Zellen, und Pandocs HTML-Leser erkennt `$…$` in Zellen nicht (Versuch
10.11.2026). Deshalb `export.office`:

1. `markdown_zu_bloecken(db, {schlüssel: markdown})` liest alle Zellen in **einem** Pandoc-Aufruf
   (je Teil ein `::: {#tN}`-Abschnitt) zu Pandoc-Blöcken — mit Diagramm-Prärender, Klammer-Mathe
   und HTML-Regel, also im Dialekt der Werkstatt. Ein Teil mit einer Zeile aus drei Doppelpunkten
   wird einzeln gelesen; sie schlösse sonst den Abschnitt.
2. Der Export baut das Dokument mit `ueberschrift`, `absatz`, `tabelle` (Spaltenanteile) und
   `durchstreichen` zusammen (`lesson_export.export_office`, `curriculum_export.render_curriculum_office`).
3. `dokument_zu_office` schreibt es. Die `pandoc-api-version` stammt immer aus Schritt 1 und passt
   deshalb zum installierten Pandoc (Prod 3.11, lokal 3.13).

Pandoc kann keine Zellfarben setzen: Die Priorität im Stundenentwurf steht seit 0.39 als Kürzel
mit Legende (`PRIO_LEGENDE`). `python-docx` ist entfallen.

⚠️ **Pandoc schreibt Tabellen ohne Linien** — im ODT ausdrücklich (`fo:border="none"` an den
Zellstilen), im DOCX über die rahmenlose Formatvorlage „Table“. In der Textverarbeitung sah das aus
wie Text mit Tabulatoren. `export.nachbearbeitung.nachbearbeiten` setzt nach jedem Office-Export
(auch Werkstatt) Rahmen direkt an Tabelle bzw. Zellen und dreht mit `quer=True` die Seite
(Curriculum). Es bearbeitet die fertige Datei, nicht die Vorlage — Schulvorlagen bleiben gültig.

## Vorlagen-Governance (Schritt 6)

`export.templates`: PDF-**CSS** in `site_config` (`export_css`) → `extra_css` im Template;
DOCX/ODT-**reference-doc** auf Disk (`EXPORT_TEMPLATE_DIR`, cwd-unabhängig). Admin-Router
`app/api/admin/export_templates.py` (`require_role("admin")`). `vorlage(fmt)` liefert die Vorlage der
Schule oder die **eingebaute**: Pandocs eigene, beim ersten Gebrauch auf A4 umgeschrieben
(`eingebaute_vorlage`). ⚠️ Pandocs reference.odt ist US-Letter, die reference.docx legt kein Format
fest. Erzeugt statt mitgeliefert, damit sie zur installierten Pandoc-Fassung passt.
⚠️ Pandoc 3.11 (Prod, CI) übernimmt das `pgSz` dieser Vorlage nicht ins DOCX, 3.13 schon. Deshalb setzt
`nachbearbeitung._docx_seitenformat` A4, wenn das fertige DOCX kein Seitenformat hat; ein Format der
Schulvorlage bleibt. Tests, die XML vergleichen, prüfen Attribute einzeln — Reihenfolge und Leerraum
hängen an der Pandoc-Fassung.

## Frontend

`lib/api.js` (`createDocument`/`getDocument`/`updateDocument`, `getDocumentExportBlob`/
`saveDocumentExport`, Admin-Vorlagen-Funktionen) · `lib/workshop.js` `deriveDocTitle` ·
Editor-Route `(app)/library/[id]/edit` (Textarea ⇄ Vorschau via `renderMarkdown` +
`renderDiagrams` + `renderServerBlocks`, Export-Leiste) · Admin-Seite `(admin)/settings/export`.
Einstieg aus dem Chat: `MessageBubble` „Als Dokument bearbeiten" — der Knopf nennt die
Tätigkeit, die Ansicht heißt weiter Werkstatt (Entscheidung zu 0.12).
