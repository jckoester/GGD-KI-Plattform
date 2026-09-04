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
| `embedding.py` | Einbettung der Knoten (welche Typen, siehe `app/context/taxonomy.yaml`) |

**Die drei Verfahren** beantworten verschiedene Fragen und dürfen deshalb nicht
verrechnet werden:

- **Identifikation** — „diesen Baustein". Titelabgleich in zwei Stufen: exakt über den
  normalisierten Titel, dann Trigramm-Teiltreffer. Nur sie zählt (`gesamt`) und trägt
  damit die Auskunft, ob es einen Baustein dieses Namens gibt. Für den `@`-Shortcode
  kommt eine dritte Stufe dazwischen (`praefix=True`): Titel, die mit dem Getippten
  **anfangen** — siehe „Warum der `@`-Weg anders ist" unten.
- **Thematische Auswahl** — „was passt dazu". Vektorsuche, **nie** vollständig, ohne
  Gesamtzahl.
- **Aufzählung** — „alle, die …". Deterministische Filterabfrage mit Zählung vor dem
  Limit, Fassungs-Deduplizierung und Gruppierung.

Jeder Abschnitt hat sein **eigenes Budget** (`Suchprofil`). Das ist keine Kosmetik: Ein
gemeinsames Limit hieße, dass Namenstreffer die thematischen verdrängen — der Fehler, der
die Neukonzeption ausgelöst hat.

**Aufruferprofile** statt getrennter Suchwege — alle über dieselbe Schicht:

| Profil | Verfahren | Budget je Abschnitt |
|---|---|---|
| Suchseite (`/knowledge/search`) | alle drei; Aufzählung, sobald eine Facette gesetzt ist | 25 |
| Vorschlagsfenster (Suchknopf im Chat) | Identifikation + thematisch | Anzeigezahl aus dem Nutzerprofil |
| `@`-Shortcode im Chat | **nur** Identifikation, mit Präfix-Stufe (`identification_only`) | Anzeigezahl, clientseitig auf 8 gekürzt |
| Werkzeug `search_context_nodes` | Identifikation + thematisch | `ASSISTANT_CONTEXT_LIMIT` |
| Werkzeug `list_context_nodes` | Aufzählung | `ASSISTANT_CONTEXT_LIMIT` |
| Assistent mit Wissensbereich | thematisch im Teilgraphen | `_ANKER_TOP_K` |

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
| `PRO_ABSCHNITT_VORAUSGEWAEHLT` = 5 | `frontend/src/lib/umschlag.js` | Wie viele Treffer je Abschnitt im Vorschlagsfenster **vorausgewählt** sind (ähnlich benannte: keine). Betrifft nicht, was gefunden wird, sondern was ohne Zutun im Prompt landet |

Zur letzten Zeile: Bis 09/2026 war **alles** vorausgewählt. Gemessen mit „nennen" bei
Anzeigelimit 30 waren das 59 Bausteine — der Operator steht in jedem Fach und in
mehreren Bildungsplan-Fassungen. Viele Gleichnamige heißen nicht „alle gemeint", sondern
„der Name war mehrdeutig"; deshalb ist auch der Namensträger-Abschnitt gedeckelt. Die
Reihenfolge innerhalb des Abschnitts entscheidet dabei mit — Fach- und Rollenbonus
stellen nach vorne, was zum Fach der Konversation gehört.

### Was gefunden werden kann

| Ort | Wirkung |
|---|---|
| `app/context/taxonomy.yaml`, `embedding: true` je content_type | Entscheidet, ob ein Knotentyp **thematisch** auffindbar ist. Ohne Embedding bleibt er über Name und Aufzählung erreichbar, taucht aber in keiner Ähnlichkeitssuche auf. Seit 09/2026: 27 von 41 Typen |
| `app/context/taxonomy.yaml`, `embedding_input` je content_type | Woraus der Vektor gebildet wird — die **einzige** Stelle, an der sich etwas gezielt weglassen lässt (Stundenentwurf: Thema statt Verlaufsplan). Ändern entwertet bestehende Vektoren dieses Typs und verlangt einen Re-Embed |
| `ROLLEN_TYP_BONUS` | `context/taxonomy.py` | Rollenabhängiger Vorsprung je Bausteinart (≤ 0,05, Bildungsplan-Typen neutral). Ein Vorzug, kein Filter — Rechte regelt `visibility.py` |
| `lookup.py`, `GENERISCHE_WOERTER` | Wörter, die bei der Begriffsbildung wegfallen („Operator", „Bedeutung", Artikel …). Betrifft **nur** den exakten Abgleich — die Teilsuche bekommt die Rohanfrage |

⚠️ **Der Eigentümer-Bonus und die rollenbasierte Gewichtung hängen an derselben
Vorbedingung: Der Typ muss überhaupt ein Embedding tragen.** Ein Bonus auf etwas, das in
der thematischen Auswahl nie erscheint, tut nichts. Bis zur Embedding-Ausweitung
(ADR-017) galt das für **alle** nutzererzeugten Bausteine — Arbeitsblätter, Klausuren und
Stundenentwürfe waren dort strukturell unsichtbar, und die Gewichtung lief leer. Heute
tragen 27 der 41 Typen ein Embedding; die 14 übrigen bleiben bewusst draußen und sind
über Name und Aufzählung erreichbar. Wer daran etwas ändern will, ändert zuerst die
Taxonomie und lässt den Embedding-Backfill laufen.

---

## Warum der `@`-Weg anders ist

Der `@`-Shortcode im Chat ist **Namensvervollständigung**, nicht Suche: Man tippt einen
Titel, den man kennt. Zwei Abweichungen folgen daraus, beide gemessen am 01.09.2026.

**Keine thematische Auswahl** (`identification_only`). Sie kostet einen Netzaufruf zum
Embedding-Modell — rund 370 ms, über den Master-Key aufs Systembudget. Das Dropdown fragt
bei jedem Tastendruck neu und zeigt von den thematischen Treffern keinen einzigen; sie
wären weder gewollt noch sichtbar, nur bezahlt.

**Eine Präfix-Stufe** zwischen exaktem Abgleich und Trigramm (`identifikation(…,
praefix=True)`). ⚠️ **Ohne sie wäre der Umbau ein Rückschritt** — die Trigramm-Ähnlichkeit
ist längennormiert, ein kurzer Titelanfang gegen einen langen Titel fällt unter
`_TEILTREFFER_SCHWELLE`:

```
„Satz"                → ohne Präfix-Stufe: 0 Treffer   (similarity ≈ 0,25 < 0,50)
„Satz des"            → ohne Präfix-Stufe: 0 Treffer
„Satz des Pythagoras" → [exakt] Satz des Pythagoras
```

Wer einen bekannten Titel von vorne tippt, sähe also bis zum letzten Wort nichts. Mit der
Stufe greift jeder Zwischenstand. Sortiert wird darin nach **Titellänge**: Bei „Satz"
steht der kurze Titel vor dem Kompetenztext, der genauso anfängt und drei Zeilen
weitergeht.

Die drei Stufen decken zusammen ab, was der frühere `ILIKE`-Weg konnte, und ordnen es
besser:

| Getippt | Stufe | Ergebnis |
|---|---|---|
| `Satz des Pythagoras` | exakt | der Namensträger, mit Existenzaussage |
| `Satz` | präfix | Titel, die so anfangen — kürzeste zuerst |
| `Pythagoras` | trigramm | Wort mitten im Titel: „Satz des Pythagoras" |

**Was dabei schwächer wird:** ein **kurzes** Wort in einem **langen** Titel. Gemessen
liegt „zwirbeln" gegen „Anleitung zum Zwirbeln von Draht" bei 0,28 — der frühere
Teilstring-Abgleich fand das, die drei Stufen finden es nicht. Zeigt sich das als
Problem, wäre eine vierte, deutlich nachrangige Teilstring-Stufe **nur für `@`** der
Ausweg; sie holt aber auch die Treffer zurück, die den Begriff bloß erwähnen (`@Pythagoras`
lieferte früher zwei Kompetenztexte vor dem gesuchten Knoten).

Die Auslöser-Regel steht im Frontend (`frontend/src/lib/mention.js`): Leerzeichen sind
erlaubt — Titel sind mehrwortig —, und das Dropdown schließt bei `esc`, bei der Auswahl
und wenn nichts mehr trifft. Der letzte Fall ist Pflicht, nicht Kosmetik: Solange das
Dropdown offen gilt, fängt der Chat die Eingabetaste ab.

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
| Erwarteter Knoten gefunden | Wird der gesuchte Baustein überhaupt geliefert | 30/39 |
| Recall@10 | Wächter gegen einen wiederkehrenden Vektorindex | 100 % |
| Aufzählungen wie erwartet | Zählung und Fächerzahl der Filterabfrage | 2/2 |
| Anker-Fälle (`anker:`) | Suche im Teilgraphen eines Assistenten — erstmals gemessen | 2/2 auf Rang 1 |
| Deckel `IDENT_DECKEL` = 3 | Wie viele Namensträger ein **thematischer** Fall höchstens erzeugen darf | derzeit 0 |

**Unterschreiten ist ein Fehlschlag, kein Kompromiss.** Wer eine Kennzahl bewusst
opfert, begründet das im Code-Kommentar neben dem geänderten Wert — so wie es die
bestehenden Konstanten vormachen.

⚠️ **Sechs Fälle schlagen absichtlich fehl.** Der Abschnitt **S8** („Methoden thematisch
finden, ohne den Namen zu kennen") misst gegen Knoten, deren Kurzbeschreibung noch
aussteht (AP6, Zulieferung 1). Ohne Beschreibung sind sie als `unvollstaendig` markiert
und haben gar keinen Vektor — die Fälle sind die **Abnahme** dieser Zulieferung, nicht
ihr Ergebnis. Deshalb steht in der Tabelle 30/39 und nicht 36/39.

### Wo die Zeit hingeht

Gemessen am Entwicklungsbestand (01.09.2026, LiteLLM lokal):

| Schritt | Dauer |
|---|---:|
| **Embedding der Anfrage** (Netzaufruf zum Modell) | **~370 ms** |
| Identifikation (exakter Abgleich + Trigramm) | ~50 ms |
| Thematische Auswahl (nur Datenbank) | ~30 ms |
| Aufzählung | ~15 ms |

Die Datenbank ist nicht der Engpass. Wer eine Suche schneller machen will, muss den
Netzaufruf **vermeiden**, nicht die Abfragen optimieren.

Zwei Dinge tun das bereits:

- **Der Netzaufruf überlappt die Identifikation.** `suche()` stößt das Embedding als
  Task an und lässt die Titelabfragen laufen, während es unterwegs ist — spart rund
  50 ms bei Nachschlage-Anfragen (484 → 431 ms, deterministisch gemessen).
- **Die Suchseite merkt sich ihr Ergebnis** für die Dauer der Sitzung
  (`frontend/src/lib/suche_cache.js`). Wer einen Treffer öffnet und zurückkommt,
  wartet nicht erneut.

⚠️ **Nur der Netzaufruf darf überlappen, nie zwei Datenbankabfragen.** Eine
`AsyncSession` verträgt das nicht und endet in `IllegalStateChangeError`. Ein `gather`
über zwei DB-Aufrufe kann trotzdem lange gutgehen — nämlich solange einer von beiden
zuerst auf das Netz wartet und dem anderen die Verbindung überlässt. Genau so stand es
bis 09/2026 im Anker-Weg; ein schnelleres Embedding hätte es umgeworfen. Ein Unit-Test
hält beide Module jetzt frei von `asyncio.gather`.

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
