# Modelle & Assistenten

## Modelle freischalten (`/settings/models`)

Die Modell-Freischaltungsmatrix legt fest, welche KI-Modelle welchen
Nutzergruppen zur Verfügung stehen. Zeilen entsprechen den in LiteLLM
konfigurierten Modellen, Spalten den Nutzergruppen (Jahrgänge und Rollen).

**Solange die Matrix leer ist, können Nutzer:innen keine Anfragen stellen.**
Nach jeder Erstinstallation und nach dem Anlegen neuer LiteLLM-Teams daher
immer zuerst die Matrix befüllen.

**Empfohlene Vorgehensweise:**

1. `/settings/models` aufrufen.
2. Für jede Nutzergruppe mindestens ein Modell aktivieren.
3. Speichern — die Änderungen sind sofort wirksam.

Als Einstiegspunkt empfiehlt es sich, zunächst ein einzelnes,
kostengünstiges Modell für alle Gruppen freizuschalten und die Matrix
später gezielt zu erweitern.

## Bildgenerierung: Bild-Modelle & Bild-Assistenten

Bildgenerierung ist an **zwei Schlüssel** gebunden — beide müssen gesetzt sein, damit
im Chat tatsächlich Bilder entstehen:

1. **Bild-Modell für die Gruppe freigeschaltet.** Auf `/settings/models` gibt es unter
   den Chat-Modellen einen zweiten Abschnitt **„Bild-Modelle"**. Er erscheint nur, wenn
   in LiteLLM ein Bild-Modell mit `model_info.mode: image_generation` konfiguriert ist.
   Beide Matrizen schreiben in dieselbe LiteLLM-Team-Allowlist — die Freigaben werden
   gegenseitig **bewahrt** (das Speichern der Chat-Matrix wischt Bild-Freigaben nicht weg
   und umgekehrt).
2. **Assistent mit der Werkzeug-Gruppe `image_generation`.** Im Assistenten-Editor die
   Checkbox **„Bildgenerierung"** aktivieren (siehe [Werkzeug-Gruppen](#werkzeug-gruppen-tool_groups)).

**Nutzerseitige Auffindbarkeit:** Assistenten mit Bildgenerierung erscheinen zusätzlich
unter dem Seitenleisten-Menüpunkt **„Werkzeuge"** (`/tools`), der alle
artefakterzeugenden Assistenten bündelt.

**Jugendschutz-Prüfpunkt:** Ein **schulweiter**, für Schüler:innen sichtbarer
Bild-Assistent geht **immer** in die Admin-Freigabe (`pending_review`) — auch wenn der
allgemeine Schalter für schulweites Teilen aus ist. Details in
[Content-Moderation → Bild-Assistenten](content-moderation.md).

**Lokaler Bild-Fallback (sensibler Pfad):** Analog zum Ollama-Chat-Fallback kann ein
lokaler, OpenAI-kompatibler Bild-Server (z. B. vLLM-Omni) als Bild-Modell in LiteLLM
eingetragen werden (`infra/litellm_config.yaml`, `model_info.mode: image_generation`).
Der Client fordert stets Base64 an — es werden **keine** extern gehosteten Bild-URLs
verarbeitet, die Bytes bleiben im Schulnetz. Vor dem Produktivbetrieb end-to-end testen.

**Kosten:** Bildgenerierung läuft über das **bestehende** USD-Budget der Nutzer:innen
(kein separates Kontingent). Siehe [Budget-System → Bildgenerierung](budget.md).

## Assistenten anlegen (`/assistants/manage/new`)

Assistenten sind vorkonfigurierte Chat-Umgebungen mit einer bestimmten Rolle
oder Aufgabe. Admins und Lehrkräfte können Assistenten anlegen.

**Felder beim Anlegen:**

| Feld | Beschreibung |
|------|-------------|
| Name | Wird Nutzer:innen angezeigt |
| Beschreibung | Kurze Erklärung des Zwecks |
| System-Prompt | Anweisung an die KI — legt Verhalten und Rolle fest |
| Modell | Leer: Nutzer wählt frei. Gesetzt: Modell ist fix für diesen Assistenten |
| Icon / Farbe | Optische Unterscheidung in der Übersicht |

**Test-Chat:** Beim Bearbeiten eines Assistenten steht direkt ein Test-Chat
zur Verfügung. Änderungen am System-Prompt können so ausprobiert werden,
bevor sie gespeichert werden.

## Unterrichtsplanung-Assistent einrichten

Der Jahresplan-Assistent ermöglicht es Lehrkräften, ihren Jahresplan per
Konversation zu erstellen. Er liest Lehrplan und Slot-Angebot, schlägt eine
UE-Verteilung vor und schreibt den Plan nach Bestätigung direkt in die
Plattform.

**Voraussetzung:** UP-Phase-1 und UP-Phase-2 müssen aktiv sein (Datenmodell
und Planer-UI), der Bildungsplan muss für die betreffenden Fächer importiert
sein.

**Einmalige Einrichtung (Seed-Skript):**

```bash
cd backend
python scripts/seed_assistants.py
```

Das Skript liest `config/assistants.yaml` (bzw. `config/assistants.example.yaml`)
und legt alle darin definierten Assistenten an, sofern noch kein Assistent
gleichen Namens existiert. Mit `--dry-run` kann man vorab prüfen, was angelegt
würde.

Danach muss der Admin nur noch das gewünschte LLM-Modell einstellen:

1. `/assistants/manage` aufrufen.
2. „Jahresplanung" in der Liste anklicken.
3. Im Feld **Modell** ein tool-fähiges Modell eintragen, z. B. `claude-sonnet-4-6`.
4. Speichern.

> **Hinweis:** Das Skript setzt `model: claude-sonnet-4-6` aus der YAML-Datei
> als Standardwert. Soll ein anderes Modell verwendet werden, einfach im
> Assistenten-Editor ändern.

**Verhalten in der UI:** Öffnet eine Lehrkraft die Planungsansicht einer
Unterrichtsgruppe und klickt auf „Assistent", wird der Chat mit diesem
Assistenten automatisch vorausgewählt. Existieren mehrere Assistenten mit
aktivierter Unterrichtsplanung, wird der erste in der Sortierreihenfolge
verwendet.

### Werkzeug-Gruppen (`tool_groups`)

Welche Planungs-Werkzeuge ein Assistent erhält, steuert das Feld `tool_groups`:

| Gruppe | Werkzeuge | Freischaltung |
|---|---|---|
| `planning` | Plan lesen/schreiben: Slots, UE-Zuordnung, Themen, Kategorien sowie der **Verschiebe-Dialog** (`get_reflow_context`, `apply_plan_operations`, `undo_last_change`) | nur **Lehrkräfte** der Gruppe, Chat mit Gruppenbezug |
| `student_planning` | nur lesend `get_exam_scope` (Termin + Umfang der nächsten Klassenarbeit) | jede:r mit Gruppenbezug — auch **Schüler:innen** |
| `image_generation` | Bildgenerierung im Chat (`generate_image`) | Assistent führt die Gruppe **und** ein Bild-Modell ist fürs Team freigeschaltet; schülersichtbare schulweite Bild-Assistenten erst nach Admin-Freigabe |

Schreibende Planungs-Werkzeuge bleiben damit strikt an die Lehrkraft-Rolle gebunden;
für Lernplan-/Prüfungsvorbereitungs-Assistenten von Schüler:innen genügt
`student_planning`.

### Verschiebe-Assistent einrichten

Der Verschiebe-Assistent hilft Lehrkräften, den Plan bei Ausfall, Verschiebungen
oder offenen Phasen neu zu ordnen. Er nutzt **dieselbe** Werkzeug-Gruppe `planning`
wie der Jahresplan-Assistent, aber einen eigenen System-Prompt:

1. Einen Assistenten anlegen (oder den bestehenden Planungs-Assistenten erweitern).
2. `tool_groups` enthält **`planning`**.
3. Als System-Prompt den Inhalt von `config/prompts/verschiebe_assistent.md` setzen.
4. Ein tool-fähiges Modell wählen (z. B. `claude-sonnet-4-6`).

Die Auslöser in der Planungs-UI (Ausfall-Banner, Drag & Drop einer geplanten Stunde,
Halbjahres-Hinweis, Überhang-Hinweisleiste) öffnen jeweils einen Chat mit
Gruppenbezug und vorbefülltem Anliegen — ein freigeschalteter Assistent mit
`planning` ist Voraussetzung, damit die Werkzeuge greifen.

## Assistenten freigeben (`/settings/assistants`)

Neu angelegte Assistenten sind zunächst nicht öffentlich sichtbar. Die
Freigabe erfolgt unter `/settings/assistants`:

- **Aktiviert:** Der Assistent ist für Nutzer:innen sichtbar und startbar.
- **Deaktiviert:** Der Assistent ist nur für Admins und Lehrkräfte sichtbar
  (z. B. für Assistenten in Entwicklung).

Die Sichtbarkeit kann pro Assistent gesteuert werden. Eine granulare
Freigabe nach Rolle oder Jahrgang ist in einer späteren Version geplant.
