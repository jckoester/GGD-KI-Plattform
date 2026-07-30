# Artefaktbibliothek (Phase 18)

Persönlicher, **lifecycle-unabhängiger** Speicher für Bilder und gerenderte Diagramme. Anders
als `generated_images` (konversationsgebunden, stirbt per FK-Cascade mit der Konversation)
überlebt ein Artefakt die Konversation bewusst. Code in `backend/app/artifacts/`.

## Datenmodell (`artifacts`, Alembic 0037/0038)

| Feld | Zweck |
|------|-------|
| `owner_pseudonym` | Eigentümer:in (Pseudonym aus dem JWT) |
| `kind` | `image` \| `circuit` \| `plot` \| `mermaid` \| `ggb` \| `document` (feingranular) |
| `mime_type`, `byte_size` | Auslieferung + Quota-Rechnung |
| `title`, `source` | Anzeige + **roher Quelltext** (Prompt bzw. Diagramm-Code) |
| `origin_ref` | Herkunfts-**Idempotenzschlüssel**; partieller Unique-Index `(owner, origin_ref)` |
| `origin_conversation_id` | nur Herkunfts-Notiz (**kein** FK/CASCADE) |
| `expires_at` | Aufbewahrung, **beim Speichern eingefroren** |

Die Bytes liegen auf Disk unter `settings.artifact_storage_dir`; `store.storage_dir()` löst
relative Pfade **repo-root-relativ** auf (cwd-unabhängig — der Cron läuft nicht aus `backend/`).

## Speichern & Idempotenz (`store.py`)

`save_artifact(...)` prüft die Per-User-Quota (`used_bytes`), schreibt die Datei und legt die
Row an, wobei `expires_at = now + retention_days` aus `limits.get_artifact_limits(roles, grade)`
eingefroren wird — so braucht der Cleanup **keinen** Rollen-Lookup.

`origin_ref` macht das Speichern **idempotent**: existiert bereits ein Artefakt gleicher Herkunft
(`find_by_origin_ref`), wird es unverändert zurückgegeben — kein zweiter Disk-Write, kein
Quota-Verbrauch. Der partielle Unique-Index ist der DB-Backstop gegen Doppelklick-Races
(`IntegrityError` → Datei verwerfen, bestehendes Artefakt zurückgeben).

## Promotion aus dem Chat (`promote.py`)

„In Bibliothek speichern" hebt einen flüchtigen Chat-Inhalt in die Bibliothek:

- **Bild** — Bytes aus `generated_images` kopieren; der Bild-Prompt (`GeneratedImage.prompt`,
  seit 0038) wandert als `source` mit. `origin_ref = image:<image_id>`.
- **circuit / plot** — **serverseitig** aus `source` neu gerendert (`render.service.render`,
  nutzt den Render-Cache); der Client-SVG wird bewusst **nicht** vertraut.
- **mermaid** — es gibt keinen Server-Renderer; der bereits im Browser gerenderte SVG wird
  übernommen. `origin_ref = <kind>:<svg_hash(kind, source)>`.

## Endpunkte (`router.py`, Prefix `/artifacts`)

| Route | Zweck |
|-------|-------|
| `POST /from-image` | Bild promoten (403 fremd · 409 Quota · 422 Fehler) |
| `POST /from-diagram` | Diagramm promoten (circuit/plot/mermaid) |
| `GET /` | eigene Bibliothek: `{ items[], used_bytes, quota_bytes }` |
| `GET /{id}` | Bytes ausliefern (Eigentümer:in); SVG mit CSP `sandbox` + `nosniff` gehärtet |
| `DELETE /{id}` | Artefakt löschen (Row + Datei) |
| `POST /ggb` | Plot-Spec → `.ggb` (zustandslos, Chat-Download) |
| `GET /{id}/ggb` | gespeichertes Plot-Artefakt → `.ggb` |

## GeoGebra-Export (`geogebra.py`)

`plot_spec_to_ggb_xml(spec)` baut das `geogebra.xml` einer `PlotSpec` (Funktionen → gelabelte
`<expression>` + `<element type="function">`; Punkte; EuclidianView-Fenster aus `domain`/`range`;
Gitter; Asymptoten). Funktionsnamen werden Plot→GeoGebra übersetzt (`**`→`^`, `log`→`ln`,
`log10`/`lg`→`lg`, `sign`→`sgn`). `ggb_bytes_from_source` verpackt es als ZIP (`.ggb`). Umfang
bewusst schmal (Funktionen/Punkte/Wertebereich) — kein Anspruch auf volle GeoGebra-Abdeckung.

## Frontend

- `lib/api.js`: `saveImageToLibrary`, `saveDiagramToLibrary`, `getLibrary`, `deleteArtifact`,
  `getPlotGgbBlob`.
- `lib/library.js`: reine Helfer (`kindLabel`, `formatBytes`, `slugify`, …).
- `lib/download.js`: `triggerDownload` (geteilt).
- `components/MessageBubble.svelte`: Speichern-Knopf an Bildern + `libraryButtons`-Action an
  gerenderten Diagrammen (inkl. GeoGebra-Knopf bei `plot`). `serverRender.js`/`diagrams.js`
  stashen die Rohquelle in `data-source`, bevor sie den Block durch SVG ersetzen.
- Route `(app)/library/+page.svelte`: Grid, Belegungsbalken, Download/PNG/Code/ggb/Löschen.
  Vorschau via `<img src="/api/artifacts/{id}">` (kein `innerHTML` → SVG-XSS-neutral).

## Cleanup

`store.cleanup_artifacts(db, now=?, dry_run=?)` löscht `expires_at < now` samt Dateien;
`scripts/cleanup_artifacts.py` ist der Cron-Einstieg. Betrieb → [Admin-Doku](../admin/artefaktbibliothek.md).
