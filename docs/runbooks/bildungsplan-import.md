# Runbook: Bildungsplan-Import

Schritt-für-Schritt-Anleitung für den Bildungsplan-Scrape und Import in den Kontextspeicher.
Gilt für Erstimport und Re-Import bei aktualisiertem Bildungsplan oder erweiterter `subjects.yaml`.

## Voraussetzungen

- Python-venv aktiv mit `requirements-scripts.txt` installiert (deckt die
  gesamte Host-Pipeline ab: Scrape, PDF-Import, Import, Embedding):
  ```bash
  pip install -r requirements-scripts.txt
  ```
  > Wer **nur scrapen** will (ohne Import/Embedding auf dem Host), kann
  > stattdessen die schlanke `scripts/scraper/requirements.txt` verwenden.
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
- LiteLLM erreichbar und bietet das unter `EMBEDDING_MODEL` konfigurierte Modell an
  (erfordert `LITELLM_PROXY_URL` und `LITELLM_MASTER_KEY` in `.env`). Zum Tauschen des
  Modells siehe [Modellwechsel](modellwechsel.md)

---

## Schritt 1 — Fächer konfigurieren

In `config/subjects.yaml` die gewünschten Fächer mit einem Bildungsplan-Fachcode
versehen. Fächer **ohne** Code werden beim Scrape/Import übersprungen (kein Fehler).

```yaml
schulart: GYM

# Welche Editionen es überhaupt gibt und ab wann sie gelten (Editions-Fahrplan).
# Steuert die ANZEIGE: /fachplan/by-subject wählt je Jahrgang die geltende Fassung.
bildungsplan_default:
  bp_basis: BP2016BW
  suffix: ""                   # globaler Fallback, falls ein Fach nichts eigenes sagt
  editionen:
    - suffix: ""               # Basis/V1 — gilt immer als Rückfallebene
    - suffix: ".V2"
      ab_schuljahr: "2016/17"
      einstieg_stufen: [5, 12]
    - suffix: ".V3"
      ab_schuljahr: "2026/27"
      einstieg_stufen: [5, 7]
      wachstum: nach_oben      # wandert jährlich eine Stufe nach oben

subjects:
  - slug: chemie
    fach_code: CH              # keine Angabe → Basisfassung
  - slug: mathematik
    fach_code: M
    bildungsplan_suffix: ".V3" # dieses Fach ist auf der dritten Fassung
```

### Zwei Schalter mit verschiedenen Aufgaben

Das ist die häufigste Verwechslung, deshalb ausdrücklich:

| | steuert | Wirkung |
|---|---|---|
| **`bildungsplan_suffix`** (je Fach) | **Scrape und Import** | welche Fassungen des Fachs geholt und eingelesen werden |
| **`editionen`** (Fahrplan) | **Anzeige** | welche Fassung in welchem Jahrgang und Schuljahr gilt |

Beide werden gebraucht. Steht ein Fach nicht auf `.V3`, wird die dritte Fassung gar nicht
erst gescrapt — der Fahrplan könnte sie dann nicht anzeigen. Umgekehrt liegt sie ohne
Fahrplan-Eintrag zwar in der Datenbank, wird aber keinem Jahrgang zugeordnet.

### Ein Fach auf eine neue Fassung stellen

Ein Feld, eine Zeile:

```yaml
  - slug: mathematik
    fach_code: M
    bildungsplan_suffix: ".V3"
```

Der Scraper holt daraufhin **alle Fassungen bis dahin**, weil ältere Jahrgänge noch auf der
vorigen unterrichtet werden und Querverweise ins Leere liefen, wenn es die alte Fassung
nicht mehr gäbe:

| `bildungsplan_suffix` | gescrapte Dateien |
|---|---|
| *(nicht gesetzt)* | `M.jsonl` |
| `".V2"` | `M_BASIS.jsonl`, `M.jsonl` |
| `".V3"` | `M_BASIS.jsonl`, `M_V2.jsonl`, `M.jsonl` |

**Die aktuelle Fassung trägt immer den schlichten Namen** (`M.jsonl`), ältere bekommen ein
Kennzeichen. Wer wissen will, was gerade gilt, schaut also stets in dieselbe Datei.

> **Prüfen statt raten:** Welche Dateien für ein Fach entstehen, lässt sich vorab
> abfragen — nützlich, bevor ein Scrape über alle Fächer läuft:
> ```bash
> python -c "
> import yaml, importlib.util as u
> s=u.spec_from_file_location('sc','scripts/scraper/bildungsplan_scraper.py')
> m=u.module_from_spec(s); s.loader.exec_module(m)
> c=yaml.safe_load(open('config/subjects.yaml')); bp=c['bildungsplan_default']
> f=[x for x in c['subjects'] if x.get('fach_code')=='M'][0]
> print(m.subject_editions(f, m.schedule_suffixes(bp), bp.get('suffix','')))"
> ```

> **Zum Schuljahr:** Ob eine Fassung *gilt*, entscheidet der Fahrplan zusammen mit dem
> laufenden Schuljahr aus `config/school_year.yaml`. Eine Edition mit
> `ab_schuljahr: "2026/27"` bleibt wirkungslos, solange dort noch `2025/26` steht.

> **Seed nach Code-Änderung:** Wird ein `fach_code` in `subjects.yaml` ergänzt oder
> geändert, die `subjects`-Tabelle neu seeden (`python scripts/seed_subjects.py`),
> damit die Cross-Fach-`#`-Bezüge den Code kennen. Wurde ein Fach **umbenannt oder
> entfernt**, zusätzlich mit `--prune` laufen lassen, um die verwaiste alte Zeile zu
> entfernen (nur unreferenzierte; siehe `docs/admin/installation.md`, Schritt 5).

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

> **Eine Datei je Fach und Edition** (`CH.jsonl`, `CH_BASIS.jsonl`) mit dem
> **vollständigen** Stand — ein Re-Scrape überschreibt sie. Die Zahlen oben sagen, wie
> viel sich geändert hat; in die Datei kommt trotzdem alles.
>
> Bis 08.08.2026 wurden nur die geänderten Knoten in eine **datierte** Datei geschrieben,
> sodass erst alle Dateien zusammen den Plan ergaben. Datierte Vorgänger desselben Fachs
> räumt der Scraper beim nächsten Lauf selbst weg.

Scrape-Warnungen prüfen:
```bash
cat scripts/scraper/output/scrape_warnings_$(date +%Y-%m-%d).log
# Strukturfehler (fehlende Tabellen etc.) müssen untersucht werden
```

> **Sonderfall LFDB (Leitfaden Demokratiebildung):** Der LFDB wird intern wie
> eine Leitperspektive geführt, hat auf der BP-Webseite aber keine Aspekt-Liste —
> seine Bausteine/Themenblöcke/Kompetenzen stehen nur in einer separaten PDF. Der
> HTML-Scraper erzeugt für LFDB daher bewusst **0 `leitperspektive_aspekt`-Knoten**
> (kein Strukturfehler) und setzt **keinen** `import_hinweis` mehr am
> Übersichtsknoten. Die PDF-Inhalte werden über den separaten **PDF-Import**
> eingespielt → Abschnitt [PDF-Import (LFDB & Fremdsprachen)](#pdf-import-lfdb--fremdsprachen).
> **Bestandssystem:** Wurde LFDB vor dieser Umstellung importiert, trägt der
> Übersichtsknoten evtl. noch einen alten `metadata.import_hinweis` — einmalig
> entfernen (siehe PDF-Import-Abschnitt).

> **Operatoren-Anhang:** Jeder Fach-Bildungsplan hat einen Anhang „Operatoren"
> (handlungsleitende Verben wie *analysieren*, *erläutern*, gegliedert nach
> Anforderungsbereichen AFB I–III). Dieser wird beim Fach-Scrape **automatisch
> mitgezogen** (Seite `…{FACHCODE}{suffix}_OP`) und als `operator`-Knoten (je
> Edition eigene, `bp_version`-getaggt) exportiert — **kein** separater Aufruf nötig.
> Titel-Synonyme („ein-, zuordnen", „(be-)nennen", „analysieren/untersuchen") werden
> zu einem kanonischen Titel + `metadata.aliase` normalisiert. Fächer ohne HTML-Anhang
> (die nur als PDF veröffentlichten Fremdsprachen Englisch/Französisch) werden vom
> HTML-Scraper übersprungen; ihre Operatoren kommen über den **PDF-Import** mit
> (identisches `operator`-Schema, siehe Abschnitt PDF-Import).

---

## PDF-Import (LFDB & Fremdsprachen)

Manche Pläne liegen **nur als PDF** vor (kein HTML) und werden **nicht** vom
Scraper (Schritt 3), sondern von der Pipeline `scripts/pdf_import/` erzeugt: der
**Leitfaden Demokratiebildung (LFDB)** und die modernen **Fremdsprachen
(Englisch `E1`, Französisch `F2`)**. Sie erzeugen **dasselbe JSONL-Format** — der
Import (Schritt 4–8) läuft danach unverändert. Die PDF wird per LLM strukturiert
(zweispaltige Tabellen, die `pdfminer` verwürfelt); die bp_id-/Node-Assemblierung
ist deterministisch.

> **Voraussetzungen:** LiteLLM erreichbar, `LITELLM_MASTER_KEY`/`LITELLM_PROXY_URL`
> gesetzt (`set -a && source .env && set +a`); Extraktionsmodell (`claude-opus-4-8`)
> unter `/settings/models` freigeschaltet. Die PDFs sind öffentlich → keine Personendaten.
> **Produktiv (Docker):** dieselben Schritte laufen im `backend`-Container, wo
> LiteLLM-Env/DB aus der Compose-Umgebung kommen — siehe
> `docs/admin/bildungsplan-import.md`, Abschnitt „PDF-Import".

### LFDB

```bash
# 1) Extraktion (LLM) → JSONL nach scripts/scraper/output/,
#    Report + Struktur nach scripts/pdf_import/output/
python -m scripts.pdf_import --lfdb \
  --source "https://.../LeitfadenDemokratiebildung/BP2016BW_ALLG_LFDB_20190712.pdf" \
  --pages "24-33"

# 2) Review-Report sichten (Baustein/Themenblock/Kompetenz-Zählung gegen die PDF)

# 3) Import mit dieser Datei (wie Schritt 4/5, aber --input auf die JSONL):
python scripts/import_bildungsplan.py --subjects config/subjects.yaml \
  --input scripts/scraper/output/lfdb.jsonl --db-url $DATABASE_URL --dry-run
python scripts/import_bildungsplan.py --subjects config/subjects.yaml \
  --input scripts/scraper/output/lfdb.jsonl --db-url $DATABASE_URL
```

Erzeugt 3 content_types: `lfdb_baustein` → `lfdb_themenblock` → `lfdb_kompetenz`
(als Unterknoten am bestehenden LFDB-Übersichtsknoten). Im Frontend:
Wissensdatenbank → Leitperspektiven (dreistufig aufklappbarer Baum).

> **Alten `import_hinweis` entfernen (einmalig, Bestandssystem).** Der
> Übersichtsknoten (`BP2016BW_ALLG_LP_LFDB`), der vor der Umstellung importiert
> wurde, trägt evtl. noch den alten Hinweis „Inhalte nur als PDF". Der Scraper setzt
> ihn nicht mehr; ein Re-Import überschreibt die Metadata aber nur bei einem erneuten
> **Leitperspektiven-Scrape+Import** (der PDF-Import berührt den Übersichtsknoten
> nicht). Ein „voller Run" ist dafür unnötig — am einfachsten direkt entfernen:
> ```sql
> UPDATE context_nodes
> SET metadata = metadata - 'import_hinweis'
> WHERE metadata->>'bp_id' = 'BP2016BW_ALLG_LP_LFDB' AND metadata ? 'import_hinweis';
> ```
> Produktiv im Container:
> ```bash
> docker compose exec db psql -U postgres -d ggd_ki \
>   -c "UPDATE context_nodes SET metadata = metadata - 'import_hinweis' \
>       WHERE metadata->>'bp_id' = 'BP2016BW_ALLG_LP_LFDB' AND metadata ? 'import_hinweis';"
> ```

### Fremdsprachen (Englisch `E1`, Französisch `F2`)

Fach-Code, Edition und PDF-URL stehen pro Fach in `config/subjects.yaml`
(`fach_code`, `bildungsplan_suffix`, `bildungsplan_pdf_url`); der HTML-Scraper
überspringt Fächer mit `bildungsplan_pdf_url`. Das Inhaltsmodell ist **identisch**
zu den HTML-Fächern (Fachplan/Leitidee/IK/PK + Operatoren aus Abschnitt 4) → sie
erscheinen in der normalen Bildungsplan-Ansicht, **kein neues Frontend**.

```bash
# 1) Band-weise Extraktion (ein LLM-Call je Jahrgangsstufe + Abschnitt 2 + Operatoren):
python -m scripts.pdf_import --fremdsprache --fach E1 --subjects config/subjects.yaml

# 2) Review-Report sichten (Bereiche/Kompetenzen je Band gegen die PDF)

# 3) Import (wie Schritt 4/5):
python scripts/import_bildungsplan.py --subjects config/subjects.yaml \
  --input scripts/scraper/output/E1_V2.jsonl --db-url $DATABASE_URL --dry-run
python scripts/import_bildungsplan.py --subjects config/subjects.yaml \
  --input scripts/scraper/output/E1_V2.jsonl --db-url $DATABASE_URL
```

Französisch analog mit `--fach F2` (→ `F2_V2.jsonl`). Re-Assemblierung **ohne**
LLM aus der gespeicherten Struktur:
`--structure-json scripts/pdf_import/output/E1_V2_struktur.json`.

> **Warum die JSONL im Scraper-Verzeichnis landet.** Ein Voll-Import läuft über **ein**
> Verzeichnis. Solange die PDF-Fächer woanders lagen, fehlten sie in jedem Voll-Import —
> und die Archivierung behandelte sie wie entfernte Knoten. Englisch und Französisch waren
> dadurch über Wochen vollständig stillgelegt (959 Knoten), ohne dass es auffiel.
> Seit 08.08.2026 schreibt der PDF-Import die JSONL nach `scripts/scraper/output/`
> (`--jsonl-dir`), Report und Struktur bleiben als Arbeitsmaterial in
> `scripts/pdf_import/output/` (`--output-dir`).
>
> Ein Schritt-4/5-Voll-Import erfasst damit **alle** Fächer; die Einzelaufrufe oben bleiben
> für den gezielten Import nach einer Extraktion.
Anschließend Embeddings (Schritt 6) und ggf. HNSW-Rebuild (Schritt 7) wie üblich.

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

Warnungs-Log prüfen — **eine Datei je Lauf**, die Uhrzeit steht im Namen. Den Pfad
nennt die letzte Zeile der Import-Ausgabe; sonst die jüngste Datei:

```bash
ls -t data/import_logs/import_warnings_*.log | head -1 | xargs cat
```

Akzeptable Warnungen: Querverweise auf Fächer die nicht in `subjects.yaml` konfiguriert sind
(z.B. BNT-Verweise aus Chemie/Physik auf andere Fächer).

Nicht akzeptabel: Warnungen mit `bp_id`-Präfixen der konfigurierten Fächer
(z.B. `BP2016BW_ALLG_GYM_CH_*`) → Fehler im Scraper oder Import, untersuchen.

---

## Schritt 6 — Embedding-Batch

```bash
# Dry-Run: zeigt Anzahl Knoten ohne Embedding
cd backend && python scripts/embedding_backfill.py --dry-run

# Echter Lauf (nach großem Erstimport: --reindex ergänzen)
cd backend && python scripts/embedding_backfill.py --reindex
```

`DATABASE_URL` muss in der `.env` oder als Umgebungsvariable gesetzt sein.

> **Gezieltes Nachziehen einzelner Typen:** Wurde nur ein content_type neu importiert
> (z. B. die Operatoren nachträglich ergänzt), lässt sich das Embedding darauf
> eingrenzen — statt den gesamten Bestand erneut zu prüfen:
> ```bash
> cd backend && python scripts/embedding_backfill.py --content-type operator
> ```
> `--content-type` ist mehrfach angebbar. Für `operator` fließt das Verb (Titel) +
> `metadata.aliase` mit in den Embedding-Text ein, damit die semantische Suche den
> Operator über sein Verb findet.

Erwartet: alle Knoten in der Whitelist haben danach `embedding IS NOT NULL`.
Prüfen:
```sql
SELECT content_type, count(*) FILTER (WHERE embedding IS NULL) as ohne
FROM context_nodes
WHERE content_type IN (
    'ik_kompetenz','pk_kompetenz','pk_gruppe','leitidee','leitperspektive_aspekt','operator'
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

> **Curricula in eine andere Instanz übertragen** (promptLab, Dev) — dafür gibt es einen
> eigenen Weg: [Curricula übertragen](curriculum-transfer.md). Dieser Bildungsplan-Import
> hier ist die **Voraussetzung** dafür: Ohne den Plan des Fachs lassen sich die
> Kompetenzverweise eines Curriculums in der Zielinstanz nicht auflösen.

## Nach Editions-Wechsel: Curricula aktualisieren (Lehrkraft-Aufgabe)

Wird ein Fach durch Re-Import auf eine neue BP-Edition umgestellt, werden die alten
IK/PK-Knoten **archiviert** und die neue Edition trägt neue `node_id`s. Bestehende
Schulcurricula zeigen dann noch auf die archivierten Knoten. **Das wird bewusst
nicht automatisch migriert** (eine neue Edition gilt stufenweise, nicht in allen
Jahrgängen gleichzeitig).

Stattdessen aktualisiert die **Lehrkraft** ein Curriculum manuell:
in der Curriculum-Ansicht → Button **„Bildungsplan aktualisieren"**. Das System
zeigt eine Vorschau und:
- verlinkt Kompetenzen mit **gleicher Nummer und weitgehend identischem Text** auf
  die neue Edition,
- markiert Kompetenzen, die es in der neuen Edition **nicht mehr gibt oder die sich
  inhaltlich geändert haben**, als **„veraltet"** (bleiben erhalten, zum Prüfen/Ersetzen),
- legt bei einem **gespaltenen Jahrgangsband** (neue Edition erst in einzelnen Stufen)
  eine migrierte **Kopie** an; das Original bleibt für die noch nicht übergegangenen Stufen.

Kein Skript, keine Admin-Aktion nötig.

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
| `0 Knoten` nach Import | Kein `fach_code` in `subjects.yaml` | `fach_code` für gewünschte Fächer setzen (Schritt 1) |
| Viele Warnungen zu konfigurierten Fächern | Scraper-Parsing-Fehler | Scraper-Log + HTML-Struktur prüfen |
| `embedding IS NULL` nach Batch | LiteLLM nicht erreichbar | `metadata_['embedding_error']` pro Knoten prüfen |
| Sequential Scan statt HNSW | Index nicht aktuell | `REINDEX INDEX idx_context_nodes_embedding` |
