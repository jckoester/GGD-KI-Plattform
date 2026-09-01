# Kontextsuche

Wie die Suche im Kontextspeicher aufgebaut ist, an welchen Zahlen man drehen kann — und
wie man prüft, ob das Drehen etwas verbessert hat.

Grundlage: `ADR-017` (Neukonzeption der Kontextsuche). Der Code liegt in
`backend/app/context/`.

---

## Aufbau

Eine Schicht, drei Verfahren, ein Ergebnisumschlag.

| Modul | Inhalt |
|---|---|
| `search.py` | Die Suchschicht: `suche()`, `identifikation()`, `thematisch()`, `aufzaehlung()`, `Suchprofil`, `Suchergebnis` |
| `visibility.py` | **Eine** Sichtbarkeitsregel für alle Abfragewege über `context_nodes` |
| `filters.py` | **Eine** Übersetzung der Feldfilter (Fach, Typ, Stufe, Titel …) — genutzt von der Aufzählung *und* von `GET /context/nodes` |
| `lookup.py` | Normalisierung von Titeln und Bildung des Nachschlage-Begriffs |
| `retrieval.py` | Nur noch der **Lernstand** (`node_engagement`). Er ist Traversierung, keine Suche — die frühere zweite Vektorsuche für Anker-Assistenten ist in `search.py` aufgegangen |
| `embedding.py` | Einbettung der Knoten (welche Typen, siehe `config/taxonomy.yaml`) |

**Die drei Verfahren** beantworten verschiedene Fragen und dürfen deshalb nicht
verrechnet werden:

- **Identifikation** — „diesen Baustein". Titelabgleich in zwei Stufen: exakt über den
  normalisierten Titel, dann Trigramm-Teiltreffer. Nur sie zählt (`gesamt`) und trägt
  damit die Auskunft, ob es einen Baustein dieses Namens gibt.
- **Thematische Auswahl** — „was passt dazu". Vektorsuche, **nie** vollständig, ohne
  Gesamtzahl.
- **Aufzählung** — „alle, die …". Deterministische Filterabfrage mit Zählung vor dem
  Limit, Fassungs-Deduplizierung und Gruppierung.

Jeder Abschnitt hat sein **eigenes Budget** (`Suchprofil`). Das ist keine Kosmetik: Ein
gemeinsames Limit hieße, dass Namenstreffer die thematischen verdrängen — der Fehler, der
die Neukonzeption ausgelöst hat.

---

## Die Stellschrauben

Alle Werte sind gemessen, nicht geschätzt. Wer einen ändert, misst neu (siehe unten).

### Ranking

| Wert | Ort | Wirkung | Wenn man ihn erhöht |
|---|---|---|---|
| `_FACHBONUS` = 0,05 | `context/search.py` | Vorsprung für Treffer aus dem Fach der Konversation, in Kosinus-Distanz | Ab 0,08 verdrängt das Fach der Konversation fachfremde Treffer, die richtig wären (Physik-Chat, Frage nach Pythagoras) |
| `_EIGENTUEMER_BONUS` = 0,05 | `context/search.py` | Vorsprung für eigenes Material in der thematischen Auswahl | Derzeit **wirkungslos**: Nutzertypen tragen kein Embedding (siehe unten) |
| `_TEILTREFFER_SCHWELLE` = 0,50 | `context/search.py` | Ab welcher Trigramm-Ähnlichkeit ein Titel als teilweise getroffen gilt | Ab 0,55 werden kurze Anfragen gegen lange Titel nicht mehr gefunden. Nach unten: Ab 0,45 bekommen thematische Anfragen Namensträger-Blöcke |

Die Boni sind **additiv und klein**, absichtlich: Sie sortieren innerhalb dessen, was
ohnehin zur Auswahl stand. Zur Einordnung — zwischen Platz 1 und Platz 10 einer
Zehnerliste liegen im Median 0,063.

### Mengen

| Wert | Ort | Wirkung |
|---|---|---|
| `ASSISTANT_CONTEXT_LIMIT` = 20 | `.env` / `config.py` | Wie viele Treffer **je Abschnitt** ein Assistent bekommt. Eine Kostenfrage: Jeder Treffer geht mit gekürztem Inhalt in den Modellkontext |
| `ANZEIGE_MIN` / `ANZEIGE_MAX` / `ANZEIGE_VORGABE` = 5 / 30 / 8 | `preferences/service.py` | Grenzen der persönlichen Einstellung „angezeigte Trefferzahl" (Suchknopf) |
| `_AUFZAEHLUNG_MAX` = 500 | `context/search.py` | Wie viele Zeilen die Aufzählung zum Zählen und Gruppieren höchstens holt. Die Zählung selbst (`COUNT(*) OVER ()`) ist unabhängig davon exakt |
| `_KANDIDATEN_FAKTOR` = 3 | `context/search.py` | Überhang beim Holen. Fassungs-Filter und -Zusammenfassung entfernen Treffer **nach** der Abfrage; ohne Überhang lieferte eine Suche mit Budget 10 am Ende womöglich vier |
| `_ANKER_TOP_K` = 10 | `context/service.py` | Wie viele Bausteine ein Assistent mit Wissensbereich in seinen Prompt bekommt. Begrenzt die Prompt-Länge, nicht die Suchgüte |
| `_INHALT_MAX_ZEICHEN` | `chat/router.py` | Auf wie viele Zeichen der Knoteninhalt fürs Modell gekürzt wird |

### Was gefunden werden kann

| Ort | Wirkung |
|---|---|
| `config/taxonomy.yaml`, `embedding: true` je content_type | Entscheidet, ob ein Knotentyp **thematisch** auffindbar ist. Ohne Embedding bleibt er über Name und Aufzählung erreichbar, taucht aber in keiner Ähnlichkeitssuche auf. Seit 09/2026: 30 von 45 Typen |
| `config/taxonomy.yaml`, `embedding_input` je content_type | Woraus der Vektor gebildet wird — die **einzige** Stelle, an der sich etwas gezielt weglassen lässt (Stundenentwurf: Thema statt Verlaufsplan). Ändern entwertet bestehende Vektoren dieses Typs und verlangt einen Re-Embed |
| `ROLLEN_TYP_BONUS` | `context/taxonomy.py` | Rollenabhängiger Vorsprung je Bausteinart (≤ 0,05, Bildungsplan-Typen neutral). Ein Vorzug, kein Filter — Rechte regelt `visibility.py` |
| `lookup.py`, `GENERISCHE_WOERTER` | Wörter, die bei der Begriffsbildung wegfallen („Operator", „Bedeutung", Artikel …). Betrifft **nur** den exakten Abgleich — die Teilsuche bekommt die Rohanfrage |

⚠️ **Der Eigentümer-Bonus und die rollenbasierte Gewichtung hängen an derselben
Vorbedingung.** `config/taxonomy.yaml` markiert 14 von 44 content_types mit
`embedding: true`, ausnahmslos Bildungsplan- und Strukturtypen. Nutzererzeugte Bausteine
(Arbeitsblätter, Klausuren, Stundenentwürfe) können in der thematischen Auswahl deshalb
gar nicht auftauchen — und ein Bonus auf etwas, das nie erscheint, tut nichts. Wer daran
etwas ändern will, ändert zuerst die Taxonomie und lässt den Embedding-Backfill laufen.

---

## Ändern und messen

**Der Prüfsatz ist verbindlich, nicht empfohlen.** Ohne ihn ist jede Änderung an der
Suche ein Blindflug: Die Unterschiede liegen oft im Hundertstelbereich und lassen sich am
Einzelfall nicht beurteilen.

```bash
cd backend

# 1. Ausgangsstand festhalten
python scripts/search_eval.py --json /tmp/vorher.json

# 2. Wert ändern …

# 3. Neu messen und vergleichen
python scripts/search_eval.py --json /tmp/nachher.json
```

Voraussetzungen: importierter Bildungsplan, laufender LiteLLM-Proxy (für das Embedding
der Anfragen), und für die S2-Fälle die Testknoten:

```bash
python scripts/seed_search_eval_nodes.py            # anlegen
python scripts/seed_search_eval_nodes.py --entfernen # wieder wegräumen
```

Der Prüfsatz (`config/search_eval.yaml`) misst drei Frageklassen und beendet sich mit
Exit-Code 1, wenn eine Zusage bricht:

| Kennzahl | Bedeutung | Ausgangswert |
|---|---|---|
| Richtiges Fach auf Platz 1 | Rangqualität der thematischen Auswahl | 17/21 |
| Erwarteter Knoten gefunden | Wird der gesuchte Baustein überhaupt geliefert | 30/33 |
| Recall@10 | Wächter gegen einen wiederkehrenden Vektorindex | 100 % |
| Aufzählungen wie erwartet | Zählung und Fächerzahl der Filterabfrage | 2/2 |
| Anker-Fälle (`anker:`) | Suche im Teilgraphen eines Assistenten — erstmals gemessen | 2/2 auf Rang 1 |
| Deckel `IDENT_DECKEL` = 3 | Wie viele Namensträger ein **thematischer** Fall höchstens erzeugen darf | derzeit 0 |

**Unterschreiten ist ein Fehlschlag, kein Kompromiss.** Wer eine Kennzahl bewusst
opfert, begründet das im Code-Kommentar neben dem geänderten Wert — so wie es die
bestehenden Konstanten vormachen.

### Messfalle

Wer Ausführungspläne oder Laufzeiten vergleicht, braucht **je Messung eine frische
Datenbankverbindung ohne Statement-Cache**. Sonst hält PostgreSQL den Plan des
vorbereiteten Statements fest, und die zweite Messung läuft mit dem Plan der ersten. Bei
der ersten Fassung des Prüfsatzes kam so für jede Anfrage ein Recall von 100 % heraus —
verglichen wurde in Wahrheit der exakte Durchlauf mit sich selbst.

---

## Verbotene Wiedergänger

In der Bestandsaufnahme widerlegt. Nicht wieder einbauen, auch nicht „zur Sicherheit":

- **Ähnlichkeitsschwellen als Gütesignal** (absolut wie relativ). Ein Abstand sagt nichts
  darüber, ob ein Treffer richtig ist. Die Trigramm-Schwelle ist etwas anderes: ein
  Abschneidekriterium des *Matchings*, kein Urteil über die Güte eines Treffers.
- **HNSW/ANN-Index auf `embedding`.** Der exakte Durchlauf ist korrekt und bis rund
  150 000 Knoten tragfähig (heute: 14 000); mit Index war die Suche messbar schlechter.
  Migration `0052` hat ihn wieder entfernt.
- **Reranker** — erst, wenn der erweiterte Prüfsatz echte Lücken zeigt.
- **„Bester Treffer" unter gleichnamigen Knoten.** Gleichnamige werden nie stumm
  gekürzt; reicht das Budget nicht, sagt der Umschlag die Gesamtzahl.

---

## Indexe und ihr stiller Ausfall

| Index | Migration | Wofür |
|---|---|---|
| `idx_context_nodes_titel_nachschlagen` | 0053 | Exakter Titelabgleich (Ausdrucksindex) |
| `idx_context_nodes_titel_trigramm` | 0054 | Teilsuche (GIN, `gin_trgm_ops`) |

Beide liegen auf **demselben** normalisierten Titelausdruck, und beide beziehen ihn aus
derselben Funktion wie die Abfrage: `app.context.lookup.titel_normalisiert_sql`.

⚠️ Weicht der Ausdruck des Index auch nur in einem Zeichen von dem der Abfrage ab,
benutzt PostgreSQL ihn **nicht** — ohne Fehler, ohne Warnung, nur langsamer. Deshalb wird
er nie abgeschrieben, und Integrationstests prüfen die Passung
(`test_chat_context_nodes.py`). Ob der Planer den Index dann auch *wählt*, hängt an der
Tabellengröße: Auf einer fast leeren Testdatenbank tut er es nicht, auf dem
Entwicklungsbestand nachweislich.

Auf `embedding` liegt **absichtlich kein Index** (siehe oben).
