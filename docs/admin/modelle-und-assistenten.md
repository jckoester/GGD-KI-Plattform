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

## Assistenten freigeben (`/settings/assistants`)

Neu angelegte Assistenten sind zunächst nicht öffentlich sichtbar. Die
Freigabe erfolgt unter `/settings/assistants`:

- **Aktiviert:** Der Assistent ist für Nutzer:innen sichtbar und startbar.
- **Deaktiviert:** Der Assistent ist nur für Admins und Lehrkräfte sichtbar
  (z. B. für Assistenten in Entwicklung).

Die Sichtbarkeit kann pro Assistent gesteuert werden. Eine granulare
Freigabe nach Rolle oder Jahrgang ist in einer späteren Version geplant.
