# Einrichtung beim ersten Login

*Seit 0.43. Plan: `Onboarding-Lehrkraefte-Plan.md` (PKM).*

Neue Lehrkräfte gehen nach dem ersten Login einen Dialog mit bis zu sechs Seiten durch:
Willkommen (Erscheinungsbild), Gut zu wissen, Umfang der Oberfläche, Stundenplan,
Unterrichtsgruppen, Fertig. Die Seiten **betten vorhandene Bausteine ein** — Kürzel-Auswahl,
Gruppenangebote, Vorschläge, Stundenraster sind dieselben Komponenten wie auf `/teaching`.
Jede Wahl speichert sofort über die bestehenden Endpunkte; die Einrichtung selbst speichert
nur ihren **Stand**.

## Backend: `app/einrichtung/router.py`

| Weg | Was |
|---|---|
| `GET /einrichtung` | alle Rollen; `faellig`, `stand`, `seite`, `stundenplan: {configured, kuerzel_gesetzt}`, `fristen: {chat_tage, konto_tage}`, `hinweis` |
| `PUT /einrichtung` | `{stand, seite}`; 403 für Rollen ohne Einrichtung und in der Vorschau (Schreibsperre) |

**Fällig** heißt: eine Rolle aus `ROLLEN` (heute nur `teacher`; Admin mit `teacher` ja, reiner
Admin nein), keine Vorschau, kein gespeicherter Stand, und `pseudonym_audit.created_at` am oder
nach `EINRICHTUNG_AB`. Konten von davor („Bestand“) bekommen den Dialog nicht von selbst, nur
über den Eintrag „Einrichtung“ und eine Neuigkeit mit Link.

- **Stand** in `user_preferences`, Schlüssel `einrichtung`:
  `{"version": 1, "stand": "spaeter"|"erledigt"|"abgewaehlt", "seite": 3, "am": "2026-11-20"}`.
  Gelesen und geschrieben nur über `einrichtung_lesen`/`einrichtung_speichern` in
  `app/preferences/service.py` — das Einstellungs-Dict verlässt das Modul nicht (es enthält das
  Stundenplan-Kürzel). Geht mit dem Konto.
- **Fristen** sind die Konstanten der Löschläufe (`_CONVERSATION_RETENTION_DAYS`,
  `_ACCOUNT_RETENTION_DAYS` in `app/crons/cleanup_service.py`); ein Test bindet sie aneinander.
- **Hinweis** ist der Site-Text `einrichtung_hinweis` (Migration 0105 legt die leere Zeile an;
  Reiter „Hinweis in der Einrichtung“ unter `/settings/texts`). Leer → `null`.
- `seite` zählt in der **vollen** Seitenliste der Rolle. Entfällt eine Seite (keine
  Stundenplanquelle), verschiebt sich der Wiedereinstieg nicht.

## Frontend

| Datei | Was |
|---|---|
| `lib/einrichtung.js` | Regeln und Texte: `SEITEN`, `SEITEN_JE_ROLLE`, `einrichtungsRolle`, `sichtbareSeiten`, `startIndex`, `sollAufgehen` (nicht unter `/help`), `gutZuWissen`, `budgetText`, `planungsStufe`, `rasterAnbieten`, `fertigZeilen`, `wegeWeiter`, `hinweisZeigen`, `hinweisText` — getestet |
| `lib/stores/einrichtung.js` | `daten` (Antwort von `GET`) und `offen`; `ladeEinrichtung`, `oeffneEinrichtung`, `schliesseEinrichtung`, `einrichtungAbwaehlen` |
| `lib/components/EinrichtungDialog.svelte` | Rahmen und Seiten; speichert „später“ beim Schließen, „erledigt“ beim Erreichen der letzten Seite |
| `lib/components/EinrichtungEintrag.svelte` | blauer Kasten zum Wiederaufruf auf `/teaching` und oben im Profil |
| `routes/(app)/+layout.svelte` | lädt `/einrichtung` für Rollen mit Einrichtung, öffnet einmal je Sitzung von selbst |
| `routes/(app)/welcome/+page.svelte` | Hinweis „Einrichtung fortsetzen“ nach „später“ (× → `abgewaehlt`) |

Die Planungsstufe (ab wann „Planung“ und das Stundenraster angeboten werden) kommt aus dem
Zuschnitt (`ui_levels.yaml`, Stufe mit Eintrag `planner`), nicht fest aus einer Zahl.

## Eine Seite dazunehmen

1. Schlüssel und Titel in `SEITEN`, Position in `SEITEN_JE_ROLLE[rolle]`. **Ans Ende vor
   `fertig` hängen** — sonst zeigt eine gespeicherte `seite` nach dem Update auf eine andere
   Seite.
2. Inhalt als `{:else if seite === '…'}` in `EinrichtungDialog.svelte`; vorhandene Bausteine
   einbetten statt nachbauen.
3. Entfällt die Seite unter Bedingungen, die Regel in `sichtbareSeiten` (mit Test).
4. `SEITEN_HOECHSTENS` im Router anheben, wenn die Liste länger wird.

## Eine Rolle dazunehmen (Schüler:innen, 0.47)

Rolle in `ROLLEN` (Backend) und `einrichtungsRolle` (Frontend), Liste in `SEITEN_JE_ROLLE`.
`EINRICHTUNG_AB` gilt für alle Rollen — für eine neue Rolle braucht es einen eigenen Stichtag,
sonst bekäme der ganze Bestand den Dialog.
