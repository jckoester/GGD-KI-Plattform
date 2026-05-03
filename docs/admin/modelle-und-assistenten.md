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

## Assistenten freigeben (`/settings/assistants`)

Neu angelegte Assistenten sind zunächst nicht öffentlich sichtbar. Die
Freigabe erfolgt unter `/settings/assistants`:

- **Aktiviert:** Der Assistent ist für Nutzer:innen sichtbar und startbar.
- **Deaktiviert:** Der Assistent ist nur für Admins und Lehrkräfte sichtbar
  (z. B. für Assistenten in Entwicklung).

Die Sichtbarkeit kann pro Assistent gesteuert werden. Eine granulare
Freigabe nach Rolle oder Jahrgang ist in einer späteren Version geplant.
