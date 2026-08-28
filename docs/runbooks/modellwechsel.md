# Runbook: Embedding-Modell wechseln

Schritt-für-Schritt-Anleitung, um das Embedding-Modell des Kontextspeichers zu tauschen —
z. B. von `text-embedding-3-small` (OpenAI) auf BGE-M3 (IONOS) oder zurück.

> **Chat-, Titel- und Bildmodelle brauchen dieses Runbook nicht.** Die lassen sich jederzeit
> über `.env` bzw. die LiteLLM-Config und die Freischaltungsmatrix umstellen, ohne
> Datenbankeingriff. Das Embedding-Modell ist der einzige Sonderfall: Es hängt an einer
> Spaltenbreite und an bereits berechneten Vektoren.

## Warum das nicht nur eine .env-Änderung ist

Zwei Dinge kommen zusammen:

1. **Die Spaltenbreite ist ein Schema-Constraint.** `context_nodes.embedding` ist
   `vector(N)`; N muss zur Ausgabebreite des Modells passen (text-embedding-3-small: 1536,
   BGE-M3: 1024).
2. **Vektoren verschiedener Modelle sind nicht vergleichbar.** Sie liegen in
   unterschiedlichen Vektorräumen — die Kosinus-Distanz zwischen einem alten und einem neuen
   Vektor ist bedeutungslos. Ein Umrechnen gibt es nicht. **Alle Knoten müssen neu
   eingebettet werden**, selbst wenn die Breite gleich bliebe.

Ein Modellwechsel ist deshalb immer: Konfiguration → Schema → Re-Embedding. In dieser
Reihenfolge, und mit einem Wartungsfenster.

## Auswirkung während der Umstellung

Zwischen dem Schema-Schritt und dem Ende des Re-Embeddings liefert die **semantische Suche
keine Treffer**. `app/context/retrieval.py` und `app/chat/router.py` filtern auf
`embedding IS NOT NULL` — es gibt also keine Fehlermeldungen, nur leere Ergebnisse:

- Der Wissensgraph-Kontext im Chat bleibt leer (Assistenten antworten weiter, nur ohne
  Kontextknoten).
- Die semantische Suche im Wissensgraph findet nichts.
- Volltext-/Titelsuche, Curricula, Unterrichtsplanung, Bildungsplan-Navigation sind **nicht**
  betroffen.

Sauberer Funktionsausfall also — aber einer, der terminiert werden muss.

## Voraussetzungen

- Backend-venv aktiv, `DATABASE_URL` gesetzt (bzw. in `.env`).
- LiteLLM-Proxy kennt das neue Modell unter dem Namen, den `EMBEDDING_MODEL` nennt
  (`model_list`-Eintrag mit `model_info.mode: embedding` und hinterlegten Preisen — sonst
  bleibt der Spend bei 0, siehe `docs/admin/konfiguration.md`).
- Wartungsfenster abgestimmt; Umfang vorher messen (Schritt 1).

---

## Schritt 1 — Umfang messen

```sql
SELECT count(*) AS neu_einzubetten
FROM context_nodes
WHERE embedding IS NOT NULL;
```

Daraus Laufzeit und Kosten des Re-Embeddings abschätzen. Bei einem vollständigen
Bildungsplan-Bestand sind das je nach Fächerzahl mehrere Tausend Knoten.

## Schritt 2 — Konfiguration umstellen

In `.env`:

```bash
EMBEDDING_MODEL=embedding-standard   # Name laut LiteLLM-Config, nicht die Anbieter-ID
EMBEDDING_DIMENSIONS=1024            # Ausgabebreite des neuen Modells
EMBEDDING_SEND_DIMENSIONS=false      # true nur bei OpenAI text-embedding-3-* (Kürzen)
```

Proxy neu starten, falls sich die LiteLLM-Config mitgeändert hat.

> **Sonderfall ohne Schema-Änderung:** OpenAIs `text-embedding-3-*` können ihre Vektoren
> kürzen. Mit `EMBEDDING_SEND_DIMENSIONS=true` und `EMBEDDING_DIMENSIONS=1024` liefert
> text-embedding-3-small direkt 1024 Dimensionen — dann entfällt Schritt 3, das
> **Re-Embedding (Schritt 4) aber nicht**.

## Schritt 3 — Spaltenbreite angleichen

Es gibt zwei Wege, je nach Situation:

### Erstinstallation / Deployment

```bash
cd backend && alembic upgrade head
```

Migration `0043` setzt die Breite auf `EMBEDDING_DIMENSIONS`. Sie ist **idempotent**: Stimmt
die Spalte schon, passiert nichts und vorhandene Embeddings bleiben erhalten.

### Wechsel im laufenden Betrieb

```bash
cd backend
python scripts/resize_embedding_column.py --dry-run   # zeigt Breite + Anzahl betroffener Vektoren
python scripts/resize_embedding_column.py             # fragt vor dem Zugriff nach
```

⚠️ **Nicht `alembic downgrade 0042 && alembic upgrade head` verwenden.** Alembic führt eine
bereits angewendete Revision nicht erneut aus, und der Downgrade würde **alle** Revisionen
oberhalb von 0042 mit aus- und wieder einbauen — also fremde Schemaänderungen anfassen. Für
Automation/Runbook-Skripte: `--yes` statt der interaktiven Rückfrage.

Beide Wege nutzen dieselbe Implementierung (`app/db/embedding_column.py`) und führen
dieselben Schritte aus:

1. HNSW-Index `idx_context_nodes_embedding` löschen (er blockiert sonst den Typwechsel).
2. `embedding = NULL` für alle Knoten — die Anzahl wird geloggt.
3. `ALTER COLUMN embedding TYPE vector(N)`.
4. HNSW-Index neu anlegen (`m=16, ef_construction=64, vector_cosine_ops`, partiell auf
   `embedding IS NOT NULL`). Billig, weil der Index nach Schritt 2 leer ist.

## Schritt 4 — Re-Embedding

```bash
cd backend
python scripts/embedding_backfill.py --dry-run                 # Anzahl prüfen
python scripts/embedding_backfill.py --batch-size 100          # eigentlicher Lauf
python scripts/embedding_backfill.py --reindex                 # HNSW-Index abschließend neu aufbauen
```

Bei großen Beständen in Tranchen fahren (`--limit`), um Last und Kosten zu verteilen. Der
Backfill nimmt sich alle Knoten mit `embedding IS NULL`, deren `content_type` einbettbar ist —
ein abgebrochener Lauf lässt sich also einfach erneut starten.

> **`--batch-size` ist nicht die Anfragegröße.** Es bestimmt, nach wie vielen Knoten die
> Datenbank-Transaktion abgeschlossen wird. Wie viele Texte in *eine* Embedding-Anfrage
> gehen, steht in `EMBEDDING_BATCH_SIZE` (Default 64). Das ist der Hebel für die Laufzeit:
> gemessen gegen BGE-M3 bei IONOS liefert ein Text je Anfrage 0,8 Knoten/s, 64 Texte je
> Anfrage 33 Knoten/s. Aus einem mehrstündigen Lauf werden damit Minuten.
>
> Antwortet der Anbieter mit `413`, `400 request too large` oder läuft in Timeouts, ist der
> Wert zu hoch — die Anfragegröße ist `EMBEDDING_BATCH_SIZE × EMBEDDING_MAX_CHARS`.
>
> **Tempo begrenzen** tut `EMBEDDING_TOKENS_PER_SECOND` (Default 3000 ≈ 180.000
> Tokens/Minute; `0` schaltet ab). Getaktet wird nach dem abgerechneten Verbrauch aus
> `usage.total_tokens`, nicht nach einer Schätzung — ein Knoten mit 15.000 Zeichen kostet
> gemessen 4500 Tokens. Den passenden Wert gibt das Rate-Limit des eigenen Anbieterkontos
> vor; ohne Drosselung läuft der Backfill auf grob 300.000 Tokens/Minute.
>
> Auf die 429-Wiederholung allein zu setzen genügt nicht: Sie greift dreimal und höchstens
> `EMBEDDING_RETRY_MAX_WAIT_S` lang. Bei anhaltender Drosselung ist das Budget erschöpft,
> die Knoten bekommen Fehlermarken, und nach drei gescheiterten Stapeln bricht der Lauf ab.
>
> Scheitert eine Anfrage mit `400`, fasst der Backfill die enthaltenen Texte einzeln nach:
> Ein unbrauchbarer Text (z. B. leer — BGE-M3 lehnt das ab, OpenAI nicht) bekommt dann
> seinen `embedding_error`, ohne die übrigen 63 Knoten mitzureißen. Bei allen anderen
> Fehlern (401, 429, Timeout) unterbleibt das: Die treffen jeden Text gleich, und nach
> **drei** vollständig fehlgeschlagenen Anfragen in Folge bricht der Lauf ab.

## Schritt 5 — Verifikation

```sql
-- Sollte nur noch nicht-einbettbare content_types enthalten
SELECT content_type, count(*) AS ohne_embedding
FROM context_nodes
WHERE embedding IS NULL AND status = 'active'
GROUP BY content_type
ORDER BY 2 DESC;
```

Zusätzlich fachlich stichprobenartig prüfen:

- Semantische Suche im Wissensgraph mit zwei bis drei bekannten Anfragen — liefert sie
  plausible Treffer?
- Ein Chat mit einem Assistenten, der Kontextknoten nutzt: erscheinen Kontextvorschläge?
- Spaltenbreite: `\d context_nodes` zeigt `vector(N)` mit dem konfigurierten N.

> **Qualität gegenprüfen, nicht nur Funktion.** Ein anderes Modell kann funktionieren und
> trotzdem schlechter treffen. Am besten vor der Umstellung eine kleine Liste typischer
> Suchanfragen mit erwarteten Treffern notieren und danach dieselbe Liste durchgehen.

---

## Rollback

```bash
# 1. .env auf die alten Werte zurücksetzen (Modell + Dimensionen + SEND_DIMENSIONS)
# 2. Spaltenbreite zurückstellen
cd backend && python scripts/resize_embedding_column.py --yes
# 3. Erneut einbetten — auch der Rückweg braucht ein vollständiges Re-Embedding
python scripts/embedding_backfill.py --batch-size 100
python scripts/embedding_backfill.py --reindex
```

Es gibt keinen Weg, die alten Vektoren zu retten: Sie wurden in Schritt 3 verworfen. Der
Rollback kostet also genauso viel wie die Umstellung.

## Wenn Konfiguration und Datenbank auseinanderlaufen

Passt `EMBEDDING_DIMENSIONS` nicht zur Spalte, greifen zwei Schutzmechanismen:

- `generate_embedding()` bricht mit `EmbeddingDimensionError` ab und nennt gelieferte
  Breite, erwartete Breite und Modellnamen — statt den DB-Insert mit einer
  pgvector-Meldung scheitern zu lassen, die die Ursache nicht erkennen lässt.
- Fehler beim Einbetten landen als `metadata.embedding_error` am jeweiligen Knoten und im
  Log; das Anlegen von Knoten schlägt deswegen **nicht** fehl (Embedding ist bewusst kein
  kritischer Pfad).

Behebung: entweder `EMBEDDING_DIMENSIONS` auf den Wert des Modells korrigieren, oder
Schritt 3 + 4 nachziehen.

## Zusammenhang mit dem Bildungsplan-Import

`docs/runbooks/bildungsplan-import.md` Schritt 6 macht dasselbe Re-Embedding, nur für neu
importierte Knoten statt für den Gesamtbestand. Nach einem Modellwechsel ist ein
Bildungsplan-Re-Import **nicht** nötig — die Knoten bleiben, nur ihre Vektoren werden neu
berechnet.
