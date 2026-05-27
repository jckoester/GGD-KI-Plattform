# Runbook: Bildungsplan-Import

Schritt-für-Schritt-Anleitung für den Bildungsplan-Scrape und Import in den Kontextspeicher.
Gilt für Erstimport und Re-Import bei aktualisiertem Bildungsplan oder erweiterter `subjects.yaml`.

## Voraussetzungen

- Python-venv aktiv mit `requirements-scripts.txt` installiert:
  ```bash
  pip install -r requirements-scripts.txt
  ```
- Backend-Package im Pfad (für Import-Skript und Embedding-Batch):
  ```bash
  export PYTHONPATH=backend
  ```
- Datenbankverbindung konfiguriert:
  ```bash
  export DATABASE_URL="postgresql+asyncpg://user:pass@localhost/ggd_ki"
  ```
- Alembic-Migrationen eingespielt:
  ```bash
  cd backend && alembic upgrade head
  ```
- LiteLLM für `text-embedding-3-small` erreichbar (erfordert `LITELLM_PROXY_URL` und `LITELLM_MASTER_KEY` in `.env`)

---

## Schritt 1 — Fächer konfigurieren

In `config/subjects.yaml` die gewünschten Fächer mit `fach_code` versehen:

```yaml
schulart: GYM
schuljahr: "2026/27"
bildungsplan_default:
  bp_basis: BP2016BW
  suffix: ""

subjects:
  - slug: chemie
    fach_code: CH
    # … restliche Felder unverändert
  - slug: mathematik
    fach_code: M
    bildungsplan_overrides:
      "5-6": ".V2"
```

Fächer ohne `fach_code` werden übersprungen (kein Fehler).

Validierung:
```bash
python -c "import yaml; yaml.safe_load(open('config/subjects.yaml')); print('YAML OK')"
```

---

## Schritt 2 — Monitor: Änderungen prüfen (bei Re-Import)

Prüft ob sich Fassungsdaten auf der Website geändert haben:

```bash
python -m scripts.scraper.monitor --subjects config/subjects.yaml
# Exit 0 → keine Änderungen
# Exit 1 → geänderte Fächer werden ausgegeben → Schritt 3 ausführen
```

Beim Erstimport diesen Schritt überspringen und direkt zu Schritt 3.

---

## Schritt 3 — Scrape

```bash
# Alle Fächer mit fach_code scrapen
python -m scripts.scraper.bildungsplan_scraper \
  --subjects config/subjects.yaml \
  --output scripts/scraper/output

# Nur ein Fach (für Tests oder gezielte Updates)
python -m scripts.scraper.bildungsplan_scraper \
  --subjects config/subjects.yaml \
  --output scripts/scraper/output \
  --fach CH
```

Erwartetes Log am Ende:
```
N neu, M geändert, K unverändert, 0 Warnungen
```

Scrape-Warnungen prüfen:
```bash
cat scripts/scraper/output/scrape_warnings_$(date +%Y-%m-%d).log
# Strukturfehler (fehlende Tabellen etc.) müssen untersucht werden
```

---

## Schritt 4 — Dry-Run des Imports

```bash
python scripts/import_bildungsplan.py \
  --subjects config/subjects.yaml \
  --input scripts/scraper/output \
  --db-url $DATABASE_URL \
  --dry-run
```

Ausgabe prüfen:
- `[DRY RUN] N insertiert, 0 aktualisiert, ...` beim Erstimport
- `[DRY RUN] 0 insertiert, M aktualisiert, ...` bei Re-Import mit Änderungen
- `[DRY RUN] 0 insertiert, 0 aktualisiert, K unverändert` bei unveränderten Daten → kein Import nötig

---

## Schritt 5 — Import

```bash
python scripts/import_bildungsplan.py \
  --subjects config/subjects.yaml \
  --input scripts/scraper/output \
  --db-url $DATABASE_URL
```

Warnungs-Log prüfen:
```bash
cat data/import_logs/import_warnings_$(date +%Y-%m-%d).log
```

Akzeptable Warnungen: Querverweise auf Fächer die nicht in `subjects.yaml` konfiguriert sind
(z.B. BNT-Verweise aus Chemie/Physik auf andere Fächer).

Nicht akzeptabel: Warnungen mit `bp_id`-Präfixen der konfigurierten Fächer
(z.B. `BP2016BW_ALLG_GYM_CH_*`) → Fehler im Scraper oder Import, untersuchen.

---

## Schritt 6 — Embedding-Batch

```bash
# Dry-Run: zeigt Anzahl Knoten ohne Embedding
python scripts/run_embedding_batch.py --db-url $DATABASE_URL --dry-run

# Echter Lauf
python scripts/run_embedding_batch.py --db-url $DATABASE_URL
```

Erwartet: alle Knoten in der Whitelist haben danach `embedding IS NOT NULL`.
Prüfen:
```sql
SELECT content_type, count(*) FILTER (WHERE embedding IS NULL) as ohne
FROM context_nodes
WHERE content_type IN (
    'ik_kompetenz','pk_kompetenz','pk_gruppe','leitidee','leitperspektive_aspekt'
)
  AND status = 'active'
GROUP BY content_type;
-- Alle ohne = 0
```

---

## Schritt 7 — HNSW-Index-Rebuild

Nach dem ersten vollständigen Batch-Import oder nach größeren Bulk-Updates:

```sql
-- Entwicklungs-DB (direkte Verbindung, single-user)
REINDEX INDEX idx_context_nodes_embedding;

-- Produktions-DB (concurrent, kein Table-Lock)
REINDEX INDEX CONCURRENTLY idx_context_nodes_embedding;
```

Im laufenden Betrieb mit kleinen inkrementellen Updates ist kein REINDEX nötig.

---

## Schritt 8 — Validierungs-Stichproben

```sql
-- Kein ik_kompetenz ohne part_of-Kante
SELECT count(*) FROM context_nodes n
LEFT JOIN context_edges e ON e.from_node_id = n.id AND e.relation = 'part_of'
WHERE n.content_type = 'ik_kompetenz' AND n.status = 'active' AND e.id IS NULL;
-- Erwartet: 0

-- Knotenzählung pro content_type
SELECT content_type, count(*), count(embedding) AS mit_embedding
FROM context_nodes WHERE status = 'active'
GROUP BY content_type ORDER BY count DESC;
```

Performance-Smoke:
```sql
EXPLAIN ANALYZE
SELECT n.id, n.content_type, n.title,
       n.embedding <=> ref.embedding AS distance
FROM context_nodes n,
     LATERAL (
         SELECT embedding FROM context_nodes
         WHERE embedding IS NOT NULL AND content_type = 'ik_kompetenz'
         LIMIT 1
     ) ref
WHERE n.embedding IS NOT NULL AND n.status = 'active'
ORDER BY n.embedding <=> ref.embedding
LIMIT 5;
-- Erwartet: HNSW Index Scan, Execution Time < 100 ms
```

---

## Schritt 9 — Scraper-State committen

```bash
git add data/scraper_state.json
git commit -m "chore: scraper_state.json nach Bildungsplan-Import aktualisiert"
```

---

## Rollback

Falls der Import Fehler erzeugt hat:

```sql
-- Alle BP-Knoten eines Fachs löschen (z.B. nach fehlerhaftem Chemie-Import)
BEGIN;
DELETE FROM context_nodes
WHERE category = 'knowledge'
  AND metadata->>'bp_id' LIKE 'BP2016BW_ALLG_GYM_CH%';
-- FK CASCADE löscht zugehörige context_edges automatisch
COMMIT;
```

Dann Scraper-JSONL korrigieren und Import erneut ausführen.

---

## Monitor-Empfehlung

Das Monitor-Skript `monitor.py` kann wöchentlich manuell ausgeführt werden:

```bash
python -m scripts.scraper.monitor --subjects config/subjects.yaml
```

---

## Fehlerbehebung

| Symptom | Ursache | Lösung |
|---------|---------|--------|
| `related_to` Constraint-Fehler | Migration 0019 nicht eingespielt | `cd backend && alembic upgrade head` |
| `0 Knoten` nach Import | Kein `fach_code` in `subjects.yaml` | `fach_code` für gewünschte Fächer setzen |
| Viele Warnungen zu konfigurierten Fächern | Scraper-Parsing-Fehler | Scraper-Log + HTML-Struktur prüfen |
| `embedding IS NULL` nach Batch | LiteLLM nicht erreichbar | `metadata_['embedding_error']` pro Knoten prüfen |
| Sequential Scan statt HNSW | Index nicht aktuell | `REINDEX INDEX idx_context_nodes_embedding` |
