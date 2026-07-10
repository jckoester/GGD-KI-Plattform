# Material-Werkstatt — Arbeitsblätter erstellen & anpassen

Die **Werkstatt** ist ein einfacher Editor, mit dem du Text-Materialien (Arbeitsblätter,
Merkblätter, Aufgabenzettel) bearbeitest und als **PDF, Word (DOCX) oder OpenDocument (ODT)**
exportierst. Ein Dokument bleibt — wie alles in der [Bibliothek](bibliothek.md) — unabhängig vom
Chat erhalten.

## Ein Dokument anlegen

Zwei Wege:

- **Aus dem Chat:** Lass dir von einem Assistenten ein Arbeitsblatt schreiben und klicke unter
  der Antwort auf **„In Werkstatt öffnen"**. Der Text wird als Dokument übernommen und der Editor
  öffnet sich. (Rahmensätze wie „Hier ist dein Arbeitsblatt:" kannst du im Editor löschen.)
- **Leer:** In der [Bibliothek](bibliothek.md) oben rechts auf **„Neues Dokument"**.

## Bearbeiten

Der Editor ist zweigeteilt: links schreibst du in **Markdown**, rechts siehst du sofort die
**Vorschau**. Markdown ist eine einfache Textauszeichnung:

| Du schreibst | Ergebnis |
|---|---|
| `# Überschrift` | große Überschrift |
| `## Abschnitt` | kleinere Überschrift |
| `**fett**`, `*kursiv*` | **fett**, *kursiv* |
| `- Punkt` | Aufzählung |
| `1. Punkt` | nummerierte Liste |
| `\| A \| B \|` … | Tabelle |
| `$x^2$` | Formel |

Diagramme, Schaltpläne und Funktionsgraphen funktionieren wie im Chat (```mermaid, ```circuitikz,
```plot) und erscheinen in der Vorschau. **Speichern** sichert das Dokument; ungespeicherte
Änderungen zeigt der Editor oben an.

## Exportieren

Über die **Export**-Leiste: **PDF**, **Word** oder **ODT**. Zwei Möglichkeiten:

- **Herunterladen** — die Datei landet in deinen Downloads.
- **„In Bibliothek behalten"** ankreuzen — die exportierte Datei wird zusätzlich in der Bibliothek
  abgelegt (praktisch für eine finale Fassung).

Wird beim Export gespeichert, exportiert die Werkstatt automatisch die aktuelle (gespeicherte)
Fassung — deine ungespeicherten Änderungen werden also zuerst gesichert.

## Gut zu wissen

- **PDF** übernimmt das schulweite Layout (sofern eingerichtet); **Word/ODT** nutzen eine
  schulweite Formatvorlage. PDF- und Word-Layout sehen ähnlich, aber nicht identisch aus — das ist
  technisch bedingt.
- **Formeln** werden in Word zu echten, bearbeitbaren Word-Formeln.
- Ein paar Feinheiten unterscheiden Vorschau und Export: **Fußnoten** (`[^1]`) erscheinen erst im
  Export als richtige Fußnote (in der Vorschau als Text); **Ankreuz-Listen** (`- [ ]`) zeigt die
  Vorschau als Kästchen, der Export als `[ ]`/`[x]`.
- Dokumente zählen wie andere Artefakte auf dein Speicherlimit und werden nach der
  Aufbewahrungsfrist automatisch entfernt — lade Wichtiges rechtzeitig herunter.
