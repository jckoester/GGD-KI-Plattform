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

> ⚠️ **Pandoc muss die Fassung mit eingebetteten Datendateien sein.** Das Image installiert
> deshalb das **offizielle `.deb`** von `jgm/pandoc` (Version über `--build-arg PANDOC_VERSION`),
> nicht das Debian-Paket: Letzteres legt die Datendateien unter `/usr/share/pandoc/data/` ab, und
> `--sandbox` verbietet genau solche Lesezugriffe. Jede Konvertierung schlüge dann fehl mit
> `Could not find data file docx/[Content_Types].xml`. Der Build prüft das selbst — er konvertiert
> ein Testdokument und bricht ab, wenn es nicht klappt. Wer Pandoc auf einem eigenen Weg
> installiert, prüft es von Hand:
>
> ```bash
> printf '# Titel\n\nText.\n' | pandoc -f commonmark_x -t docx --sandbox -o /tmp/probe.docx
> ```

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

## Herkunftszeile am Dokumentende

Auf `/settings/export` lässt sich schulweit einschalten, dass exportierte Dokumente eine
Zeile mit Werkzeug, Modell und Datum tragen:

```
Erstellt mit ki@schule · Modell gpt-oss-120b · 29.08.2026
```

Sie erscheint in **allen drei Formaten** gleich (PDF, DOCX, ODT), weil sie an das Markdown
angehängt wird und nicht per Seitenfuß gesetzt ist.

**Vorgabe: aus.** Ein Update soll das Aussehen bereits genutzter Vorlagen nicht von sich aus
verändern — ob die Angabe erscheint, entscheidet die Schule.

Zwei Einschränkungen, die kein Fehler sind:

- Die Zeile erscheint **nur bei Dokumenten aus einer KI-Antwort**. Ein von Hand
  geschriebenes Dokument mit „Erstellt mit …" zu versehen wäre eine Falschangabe; die
  Werkstatt lässt sich auch ganz ohne KI benutzen.
- Als Werkzeugname dient `PUBLIC_SCHOOL_NAME` aus der `.env` (ersatzweise
  `EXPORT_SCHOOL_NAME`). Ist keiner gesetzt, nennt die Zeile nur Modell und Datum —
  ein Platzhalter wie „diese Plattform" hilft in einem Dokument, das die Plattform längst
  verlassen hat, niemandem.

Warum überhaupt: [KI-Ergebnisse zitieren](../user/zitieren.md) und
[Modell-Szenarien → Was gespeichert wird](modell-szenarien.md#was-gespeichert-wird--und-was-zitierfähig-ist).

## Ablage & Persistenz

Die Referenzdokumente liegen unter `EXPORT_TEMPLATE_DIR` (Default `data/export_templates`; in
Docker absolut auf `/app/data/export_templates` gesetzt → auf dem gemeinsamen `./data`-Volume,
siehe [Artefaktbibliothek](artefaktbibliothek.md#ablage--volume)). In die Backup-Strategie
einbeziehen; das CSS liegt in der Datenbank (`site_config`).

## Datenschutz

Dokumente sind pseudonyme Artefakte (nur die Eigentümer:in sieht/exportiert sie) und unterliegen
demselben Lifecycle wie die übrige Bibliothek (Aufbewahrung, Cleanup-Cron, Löschung mit dem Konto).
