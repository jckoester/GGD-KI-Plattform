# Material-Werkstatt — Betrieb & Vorlagen

Die **Material-Werkstatt** (Phase 19) lässt Nutzer:innen Markdown-Dokumente (`artifacts.kind='document'`,
Teil der [Artefaktbibliothek](artefaktbibliothek.md)) bearbeiten und als **PDF / DOCX / ODT**
exportieren.

## Abhängigkeit: Pandoc

- **PDF** wird über weasyprint erzeugt (bereits für den Curriculum-Export vorhanden) — **keine**
  zusätzliche Abhängigkeit.
- **DOCX/ODT** laufen über **Pandoc**. Im Docker-Image ist `pandoc` enthalten (Dockerfile). Fehlt
  Pandoc, ist der Office-Export **automatisch deaktiviert** (Feature-Flag) — PDF und der Rest der
  Plattform funktionieren normal; ein Office-Export-Versuch meldet „nicht verfügbar" (HTTP 503).

Pandoc läuft mit `--sandbox` (kein Datei-/Netzzugriff), der Reader ist `commonmark_x` **ohne**
`raw_tex` — nutzereditierbares Markdown kann also kein LaTeX ausführen oder Dateien einbinden.

## Export-Vorlagen (schulweites Layout)

Unter **Einstellungen → Export-Vorlagen** (`/settings/export`, nur Admin):

- **PDF-CSS** — freies CSS, das die eingebaute Standard-Vorlage ergänzt/überschreibt (Schrift,
  Farben, Kopf-/Fußzeile). Wird in `site_config` (`export_css`) gespeichert.
- **Word/ODT-Referenzdokument** — je ein hochgeladenes `.docx`/`.odt`, dessen Formatvorlagen
  (Überschriften, Schriften, Ränder) Pandoc via `--reference-doc` übernimmt. Am einfachsten: ein
  bestehendes Dokument mit den gewünschten Formatvorlagen speichern und hochladen.

Fehlt eine Vorlage, greift die eingebaute Default-Optik. **PDF- und DOCX-Layout lassen sich
prinzipiell nicht exakt angleichen** (verschiedene Layout-Systeme) — „ungefähr gleich" ist das
erreichbare Ziel. Persönliche (nutzereigene) Vorlagen sind noch nicht vorgesehen.

## Ablage & Persistenz

Die Referenzdokumente liegen unter `EXPORT_TEMPLATE_DIR` (Default `data/export_templates`; in
Docker absolut auf `/app/data/export_templates` gesetzt → auf dem gemeinsamen `./data`-Volume,
siehe [Artefaktbibliothek](artefaktbibliothek.md#ablage--volume)). In die Backup-Strategie
einbeziehen; das CSS liegt in der Datenbank (`site_config`).

## Datenschutz

Dokumente sind pseudonyme Artefakte (nur die Eigentümer:in sieht/exportiert sie) und unterliegen
demselben Lifecycle wie die übrige Bibliothek (Aufbewahrung, Cleanup-Cron, Löschung mit dem Konto).
