# Werkstatt (Ablage) — Betrieb & Konfiguration

Die **Werkstatt** (bis 0.40 „Bibliothek“, technisch Artefaktbibliothek) ist ein persönlicher,
konversationsübergreifender Speicher: Nutzer:innen
heben dort Bilder und gerenderte Diagramme aus dem Chat hinein, damit sie den 90/93-Tage-Lifecycle
der Konversationen überleben. Metadaten liegen in der Tabelle `artifacts`, die Bytes auf Disk.

## Konfiguration: Aufbewahrung & Quota

Aufbewahrungsfrist und Speicher-Quota sind **role- und jahrgangsbasiert** — konfiguriert in
`config/artifact_limits.yaml` (Struktur wie `budget_tiers.yaml`). Aus `.example` provisionieren:

```yaml
grades:
  5:  { retention_days: 365, quota_bytes: 52428800 }    # 50 MB
  # … 6–12 …
  11: { retention_days: 365, quota_bytes: 157286400 }   # 150 MB

roles:
  teacher:
    retention_days: 730     # 2 Jahre
    quota_bytes: 1073741824 # 1 GB
```

- **`retention_days`** — so viele Tage nach dem **letzten Benutzen** entfernt der Cleanup-Cron
  ein Produkt. Der anwendbare Wert wird in `expires_at` eingefroren: beim Speichern und seit 0.41
  **erneut bei jedem Benutzen** — Inhalt ändern, Titel/Fach/Thema ändern, exportieren, als Baustein
  übernehmen. Die Frist wird dabei nie verkürzt. Spätere Änderungen an der YAML wirken also auf
  neu gespeicherte und auf wieder benutzte Produkte, nicht rückwirkend auf den Rest.
- **`quota_bytes`** — maximale Gesamtgröße der Werkstatt pro Nutzer:in. Ist sie erreicht,
  lehnt das Speichern mit einer klaren Meldung ab (die Nutzer:in muss erst löschen).
- **Auflösung:** `teacher` (auch `teacher`+`admin`) → `roles.teacher`; `student` →
  `grades[<Jahrgang>]`; sonst konservativer Built-in-Default. **Fehlt die Datei**, greifen
  Built-in-Defaults (Lehrkraft 730 d / 1 GB, Schüler 365 d / 50 MB) — **kein Hard-Fail**, aber
  eine Warnung im Log. Es gibt **kein UI**; die Datei wird selten geändert.

Es gibt **keine schulweite Freischaltung** — die Werkstatt steht allen eingeloggten Rollen
offen. Wer Bilder/Diagramme erzeugen darf, steuert die Modell-/Assistenten-Freigabe
(siehe [Modelle & Assistenten](modelle-und-assistenten.md)).

## Ablage & Volume

Die Bytes liegen unter `ARTIFACT_STORAGE_DIR` (Default `data/artifacts`). In Docker ist das
ein **absoluter Pfad auf einem gemeinsamen Volume**, das sich `backend` und `cron` teilen:

```yaml
# docker-compose.yml (backend UND cron)
environment:
  ARTIFACT_STORAGE_DIR: /app/data/artifacts
  IMAGE_STORAGE_DIR: /app/data/generated_images
volumes:
  - ./data:/app/data
```

Wichtig: Der Pfad **muss in beiden Diensten identisch** sein — sonst räumt der Cron ins Leere.
Das Volume `./data` sollte in die Backup-Strategie einbezogen werden (die Dateien liegen sonst
nirgends redundant).

## Cleanup-Cron

Der Cron-Container ruft täglich `scripts/cleanup_artifacts.py` auf: es löscht alle Artefakte
mit `expires_at < now` samt Datei. Seit 0.41 gehen die Exporte eines abgelaufenen Dokuments
mit (samt Dateien), auch wenn ihre eigene Frist noch läuft. Idempotent, gefahrlos wiederholbar.

```yaml
# docker-compose.yml (cron command)
45 4 * * * root python /app/scripts/cleanup_artifacts.py
```

Manuell/zur Kontrolle:

```bash
docker compose exec cron python scripts/cleanup_artifacts.py --dry-run   # nur zählen
docker compose exec cron python scripts/cleanup_artifacts.py             # tatsächlich löschen
```

Parallel läuft `cleanup_generated_images.py` (Backstop für generierte Bilder auf demselben
Volume).

## Schüler-Bausteine überführen (einmalig, 0.41)

Seit 0.41 legen Schüler:innen keine Bausteine mehr an; was sie aus dem Chat behalten, bleibt
ein Produkt in ihrer Werkstatt. Den Bestand (Bausteinarten `schuelertext`, `lernplan`,
`schuelerpraesentation`) räumt nach dem Update ein Skript einmal um:

```bash
docker compose exec backend python scripts/schueler_bausteine_ueberfuehren.py --dry-run
docker compose exec backend python scripts/schueler_bausteine_ueberfuehren.py
```

Je Baustein: Gibt es das Produkt, aus dem er übernommen wurde, noch, bekommt es Fach (und
einen Titel, falls es nur „Dokument" heißt), dann wird der Baustein gelöscht. Sonst legt das
Skript aus dem Inhalt ein Dokument an und löscht danach. Stehen bleiben Bausteine ohne
Inhalt, solche, auf die fremde aktive Bausteine verweisen, und solche, für die die Quota der
Schüler:in nicht reicht — das Protokoll nennt sie mit Kennung (ohne Titel). Gliederungen und
Mindmaps (`strukturierung`) von Personen ohne Lehrkraft-Rolle werden nur gelistet; sollen
sie ebenfalls überführt werden, mit `--mit-strukturierung` erneut aufrufen. Der echte Lauf
schreibt das Ereignis „Schüler-Bausteine in die Werkstatt überführt" mit den Zahlen ins
Audit-Log. Ein zweiter Lauf findet nur noch, was stehen blieb.

## Datenschutz

Artefakte sind **pseudonym** (`owner_pseudonym`) und werden nur an die Eigentümer:in
ausgeliefert. Beim Löschen eines Nutzerkontos werden auch dessen Artefakte entfernt (siehe
[Datenschutz & Betrieb](datenschutz-betrieb.md)). SVG-Artefakte werden mit strenger
Content-Security-Policy und `nosniff` ausgeliefert.
