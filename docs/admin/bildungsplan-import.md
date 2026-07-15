# Bildungsplan-Import (Produktivsystem)

Diese Anleitung beschreibt den Import der Bildungsplan-Daten in das **laufende
Docker-Produktivsystem**. Sie richtet sich an Admins und setzt eine fertige
Installation gemäß [Installation](installation.md) voraus.

Der Bildungsplan liefert die fachlichen Kontextdaten (Leitideen, Kompetenzen,
Leitperspektiven), die Assistenten als Wissensbasis nutzen. Ohne diesen Import
funktioniert die Plattform, der fachliche Kontext fehlt jedoch.

> **Bekannte Lücke — Leitfaden Demokratiebildung (LFDB):** Der LFDB wird intern
> wie eine Leitperspektive behandelt, auf den Seiten des Bildungsplans aber
> anders dargestellt — er hat keine „Aspekte", sondern Kompetenzen, Bausteine
> und Handlungsfelder, die **nur in einer separaten PDF** des Kultusministeriums
> liegen und nicht auf der Webseite. Der Import erzeugt daher nur den
> Übersichtsknoten **ohne Unterknoten** (0 Aspekte) und versieht ihn mit einem
> sichtbaren Hinweis (`metadata.import_hinweis`). Das ist erwartetes Verhalten,
> kein Importfehler.

> **Wann ist dieser Schritt nötig?**
> - Einmalig nach der Erstinstallation
> - Bei einem aktualisierten Bildungsplan oder erweiterter `config/subjects.yaml`
>
> Die technischen Hintergründe (Scrape-Mechanik, Datenmodell, Idempotenz) stehen
> im [Runbook Bildungsplan-Import](../runbooks/bildungsplan-import.md). Diese
> Admin-Anleitung beschränkt sich auf den Ablauf im Docker-Produktivbetrieb.

---

## Überblick

Der Import läuft in drei Etappen:

```
1. JSONL bereitstellen   (außerhalb Docker — Scrape oder vom Wartungsteam)
        │
        ▼
2. Import in die DB      (Einmal-Container im Compose-Netz)
        │
        ▼
3. Embeddings erzeugen   (im laufenden backend-Container)
```

> **Hinweis zur Architektur:** Der Scraper und das Import-Skript liegen im
> Repository-Verzeichnis `scripts/` und sind **nicht Teil des Backend-Images**
> (das Image wird nur aus `./backend` gebaut). Der Import wird deshalb über einen
> **Einmal-Container** mit eingehängtem `scripts/`-Verzeichnis ausgeführt — so
> erreicht er die Datenbank über das interne Docker-Netz (`db:5432`), ohne dass
> ein Datenbank-Port nach außen geöffnet werden muss.

Alle Befehle werden im Repository-Wurzelverzeichnis (`ki-plattform/`) auf dem
Server ausgeführt.

---

## Schritt 1: JSONL-Dateien bereitstellen

Der Import benötigt die gescrapten Bildungsplan-Daten als JSONL-Dateien im
Verzeichnis `scripts/scraper/output/`.

Diese Dateien sind **nicht im Repository enthalten** (`.gitignore`). Es gibt zwei
Wege, sie bereitzustellen:

**Variante A — selbst scrapen (Regelfall).**
Das Scrapen läuft außerhalb von Docker — die Scraper-Abhängigkeiten sind bewusst
nicht im Backend-Image, sondern in einer eigenen, schlanken
`scripts/scraper/requirements.txt` (nur `beautifulsoup4`, `lxml`, `httpx`,
`pyyaml`). Es genügt eine eigene Python-venv und Internetzugang zur
Bildungsplan-Website — kein Datenbankzugriff:

```bash
# Einmalig: venv nur für den Scraper anlegen
python -m venv .venv-scraper
source .venv-scraper/bin/activate
pip install -r scripts/scraper/requirements.txt
```

Anschließend scrapen (alle Fächer mit `fach_code` aus `config/subjects.yaml`):

```bash
python -m scripts.scraper.bildungsplan_scraper \
  --subjects config/subjects.yaml \
  --output scripts/scraper/output
```

Den vollständigen Ablauf inklusive Monitor (Änderungserkennung) und
Warnungs-Prüfung beschreibt das
[Runbook, Schritte 1–3](../runbooks/bildungsplan-import.md#schritt-2--monitor-änderungen-prüfen-bei-re-import).
Ergebnis sind die JSONL-Dateien in `scripts/scraper/output/`, z. B.:
`CH_2026-06-06.jsonl`, `M_2026-06-06.jsonl`, `M_V2_2026-06-06.jsonl`,
`leitperspektiven_2026-06-06.jsonl`.

> **Fehler pro Fach werden isoliert:** Wirft ein einzelnes Fach beim Scrapen einen Fehler
> (z. B. ungültiges Suffix/Quell-URL), wird **nur dieses Fach übersprungen** — der Lauf macht
> mit den übrigen weiter (reihenfolge-unabhängig). Übersprungene Fächer erscheinen am Ende als
> prominente Zusammenfassung im Log **und** in `scripts/scraper/output/scrape_skipped_<datum>.log`;
> der Prozess endet dann mit **Exit-Code 1**. Nach einem solchen Lauf die Liste prüfen, die
> Ursache (meist ein Config-Fehler in `subjects.yaml`) beheben und die betroffenen Fächer gezielt
> mit `--fach <CODE>` nachziehen.

**Variante B — fertige JSONL übernehmen.**
Liegen die JSONL-Dateien bereits vor (z. B. vom Wartungsteam), genügt es, sie in
das Output-Verzeichnis zu kopieren — Schritt »selbst scrapen« entfällt dann:

```bash
cp /pfad/zu/*.jsonl scripts/scraper/output/
```

> **Re-Import nach Datenmodell-Änderung:** Wurden Scraper oder Datenmodell
> geändert, **zuerst die alten JSONL-Dateien des betroffenen Fachs löschen**,
> dann neu scrapen. Der Import ist idempotent über den Content-Hash — ein altes
> JSONL ohne neues Feld würde ein neues sonst stillschweigend überschreiben.

---

## Schritt 2: Dry-Run-Import gegen die Produktions-DB

Zuerst ein Probelauf ohne Schreibzugriff. Der Befehl startet einen Einmal-Container
aus dem `backend`-Image, hängt das `scripts/`-Verzeichnis read-only ein und
verbindet sich über das Compose-Netz mit der Datenbank:

```bash
docker compose run --rm \
  -v "$(pwd)/scripts:/app/import-scripts:ro" \
  backend \
  sh -c 'python /app/import-scripts/import_bildungsplan.py \
    --subjects /app/config/subjects.yaml \
    --input /app/import-scripts/scraper/output \
    --db-url "postgresql://postgres:${POSTGRES_PASSWORD}@db:5432/ggd_ki" \
    --dry-run'
```

> Das Datenbank-Passwort wird **im Container** aus der `.env` (`POSTGRES_PASSWORD`)
> aufgelöst und erscheint nicht auf der Kommandozeile des Hosts.

Die Ausgabe prüfen:

- `[DRY RUN] N insertiert, 0 aktualisiert, ...` → Erstimport
- `[DRY RUN] 0 insertiert, M aktualisiert, ...` → Re-Import mit Änderungen
- `[DRY RUN] 0 insertiert, 0 aktualisiert, K unverändert` → keine Änderung, Import
  nicht nötig

---

## Schritt 3: Import ausführen

Sieht der Dry-Run plausibel aus, denselben Befehl **ohne** `--dry-run` ausführen:

```bash
docker compose run --rm \
  -v "$(pwd)/scripts:/app/import-scripts:ro" \
  backend \
  sh -c 'python /app/import-scripts/import_bildungsplan.py \
    --subjects /app/config/subjects.yaml \
    --input /app/import-scripts/scraper/output \
    --db-url "postgresql://postgres:${POSTGRES_PASSWORD}@db:5432/ggd_ki"'
```

> **⚠ Voll-Import archiviert Fächer ohne JSONL:** Zeigt `--input` auf ein **Verzeichnis**
> (und **kein** `--fach` ist gesetzt), archiviert der Import **jeden** aktiven BP-Knoten,
> dessen `bp_id` im aktuellen JSONL-Satz **fehlt** (`status = 'archived'`). Liegt also die
> JSONL eines Fachs gerade nicht im Verzeichnis (z. B. gelöscht und noch nicht neu gescrapt),
> wird **dieses ganze Fach archiviert**. Deshalb:
> - **Voll-Import** nur ausführen, wenn **alle** Fach-JSONLs frisch im Verzeichnis liegen.
> - Ein **einzelnes Fach nachziehen** → immer per **Einzeldatei** (`--input …/NWTBFO_<datum>.jsonl`)
>   oder `--fach <CODE>`; dann bleibt der Rest unangetastet.
>
> **Wieder aktivieren:** Ein Re-Import reaktiviert archivierte Knoten automatisch — taucht ein
> Knoten wieder im JSONL auf, setzt der Import `status` zurück auf `active`. Ein versehentlich
> archiviertes Fach lässt sich also durch erneutes (vollständiges) Scrapen + Einzeldatei-Import
> desselben Fachs zurückholen.

Warnungen prüfen — das Import-Skript schreibt sie nach
`data/import_logs/import_warnings_<datum>.log`. **Achtung:** Der Pfad ist **relativ
zum Arbeitsverzeichnis** des Skripts (im Container `/app/data/…`). Damit das Log einen
`docker compose run --rm`-Lauf überlebt, das `data/`-Verzeichnis mit einhängen
(`-v "$(pwd)/data:/app/data"`) oder die Auswertung **im selben Container** ausführen —
sonst geht die Datei mit dem Container verloren.

Die meisten Warnungen sind **erwartbar**, nicht jede ist ein Fehler:

- **Akzeptabel — Verweis auf ein nicht importiertes Fach:** Der Bildungsplan verlinkt
  quer durch den gesamten Gymnasial-Katalog; die Schule importiert nur eine Teilmenge.
  Verweise auf nicht konfigurierte/nicht gescrapte Fächer (Fremdsprachen — nur als PDF
  verfügbar; nicht angebotene Religionskonfessionen; Profilfächer) laufen daher ins
  Leere. Kein Handlungsbedarf.
- **Bekanntes Quelldaten-Rauschen — `BO_07`:** Mehrere Fächer verweisen auf den
  Leitperspektive-Aspekt `BO_07`. Die Leitperspektive Berufsorientierung hat aber nur
  **6 Aspekte** (BO_01–06); die BP-Quelle nummeriert ihren 6. Aspekt fälschlich als
  `07` (Anker-Off-by-one). Der Scraper übernimmt den Code originalgetreu → **unkritisch**,
  kein Import-/Scraper-Fehler.
- **Editionsübergang (V1/V2):** Verweise auf die **ältere Fassung** eines Fachs, das
  inzwischen auf `.V2` umgestellt ist (z. B. `…_GEO_…` statt `…_GEO.V2_…`), lösen nicht
  auf, weil nur die neue Edition importiert ist. Während der Übergangszeit erwartbar
  (siehe Versionierungs-Konzept).
- **Echter Fehler — untersuchen:** Verweis auf die **aktuelle** Edition eines
  konfigurierten, gescrapten Fachs, dessen Zielknoten fehlt (z. B. `…_CH.V2_…` ohne
  Treffer) → Scraper-/Importfehler.

---

## Schritt 4: Embeddings erzeugen

Neu importierte Knoten haben noch kein Embedding (`embedding IS NULL`) und werden
in der semantischen Suche nicht gefunden. Das Embedding-Skript liegt im
Backend-Image und läuft direkt im laufenden Container:

```bash
# Dry-Run: zeigt Anzahl Knoten ohne Embedding
docker compose exec backend python scripts/embedding_backfill.py --dry-run

# Echter Lauf (nach großem Erstimport: --reindex ergänzen)
docker compose exec backend python scripts/embedding_backfill.py --reindex
```

> **LiteLLM muss erreichbar sein** (`text-embedding-3-small`). Das Skript nutzt
> dieselbe LiteLLM-Konfiguration wie das Backend. Bei Fehlern den Eintrag
> `metadata_['embedding_error']` der betroffenen Knoten prüfen.

> **Automatik:** Der `cron`-Container füllt fehlende Embeddings ohnehin nächtlich
> (03:15 Uhr) nach. Der manuelle Lauf ist nur sinnvoll, wenn die Daten sofort
> verfügbar sein sollen.

> **Nur einen Typ nachziehen:** Wurde ein content_type nachträglich ergänzt (z. B.
> die Operatoren-Anhänge zu einem bereits importierten Bildungsplan), lässt sich das
> Embedding gezielt darauf eingrenzen:
> ```bash
> docker compose exec backend python scripts/embedding_backfill.py --content-type operator
> ```

---

## Schritt 5: HNSW-Index neu aufbauen

Nach dem ersten vollständigen Import oder größeren Bulk-Updates den Vektor-Index
neu aufbauen (im Produktivbetrieb ohne Tabellen-Sperre):

```bash
docker compose exec db psql -U postgres -d ggd_ki \
  -c "REINDEX INDEX CONCURRENTLY idx_context_nodes_embedding;"
```

Bei kleinen inkrementellen Updates im laufenden Betrieb ist kein REINDEX nötig.

---

## Schritt 6: Validierung

Stichproben gegen die Produktions-DB:

```bash
# Knotenzählung pro content_type inkl. Embedding-Abdeckung
docker compose exec db psql -U postgres -d ggd_ki -c "
SELECT content_type, count(*), count(embedding) AS mit_embedding
FROM context_nodes WHERE status = 'active'
GROUP BY content_type ORDER BY count DESC;"

# Kein ik_kompetenz ohne part_of-Kante (Erwartet: 0)
docker compose exec db psql -U postgres -d ggd_ki -c "
SELECT count(*) FROM context_nodes n
LEFT JOIN context_edges e ON e.from_node_id = n.id AND e.relation = 'part_of'
WHERE n.content_type = 'ik_kompetenz' AND n.status = 'active' AND e.id IS NULL;"
```

Nach erfolgreichem Embedding-Lauf sollte `mit_embedding` für die Wissens-Knoten
der Spaltensumme entsprechen (keine `NULL`-Embeddings).

---

## Fehlerhafte Titel korrigieren (überlebt Re-Import)

Die Bildungsplan-Quelle enthält gelegentlich fehlerhafte Kapitel-/Knoten-Titel
(Nummerierung, Schreibweise). Der Import übernimmt sie originalgetreu. **Admins** können
einen einzelnen Knoten-Titel direkt in der App korrigieren:

1. Den Knoten öffnen (z. B. aus dem Bildungsplan-Baum → Knotenansicht `/knowledge/<id>`).
2. Neben dem Titel auf das **Stift-Symbol** klicken, korrigieren, speichern.

Der korrigierte Titel wird mit `title_locked` markiert; ein **späterer Re-Import
überschreibt ihn nicht** mehr (der Quell-Titel wird ignoriert, solange die Sperre besteht).
Nur der **Titel** ist bearbeitbar — der Fließtext bleibt bewusst read-only (er käme sonst
beim nächsten Import wieder aus der Quelle). Die Bearbeitung ist auf `admin` beschränkt, da
BP-Knoten schulweit/global sind.

---

## Rollback

Erzeugte der Import fehlerhafte Daten, lassen sich alle Knoten eines Fachs gezielt
entfernen (Kanten werden per FK-CASCADE mitgelöscht):

```bash
docker compose exec db psql -U postgres -d ggd_ki -c "
BEGIN;
DELETE FROM context_nodes
WHERE category = 'knowledge'
  AND metadata->>'bp_id' LIKE 'BP2016BW_ALLG_GYM_CH%';
COMMIT;"
```

Anschließend JSONL korrigieren und den Import (Schritt 2–4) erneut ausführen.

---

## Fehlerbehebung

| Symptom | Ursache | Lösung |
|---------|---------|--------|
| `could not translate host name "db"` | Befehl nicht über `docker compose run` im Compose-Netz gestartet | Befehl exakt wie in Schritt 2/3 verwenden |
| `password authentication failed` | `POSTGRES_PASSWORD` in `.env` weicht von der DB ab | `.env` prüfen; Passwort entspricht dem bei der Installation gesetzten |
| `0 Knoten` nach Import | Kein `fach_code` in `subjects.yaml` | `fach_code` für die gewünschten Fächer setzen (siehe Runbook, Schritt 1) |
| `relation "context_nodes" does not exist` | Migrationen nicht eingespielt | `docker compose exec backend alembic upgrade head` |
| `embedding IS NULL` bleibt | LiteLLM nicht erreichbar | LiteLLM-Erreichbarkeit prüfen; `metadata_['embedding_error']` ansehen |

Tiefergehende Fehlerquellen und SQL-Diagnosen stehen im
[Runbook Bildungsplan-Import](../runbooks/bildungsplan-import.md#fehlerbehebung).
</content>
</invoke>
