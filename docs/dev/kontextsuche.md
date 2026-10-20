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
| `visibility.py` | **Eine** Sichtbarkeitsregel für alle Abfragewege über `context_nodes`. Scopes von eng nach weit: `private` · `group_teachers` · `group` · `subject` · `school` · `global`. ⚠️ **`group_teachers` verlangt zusätzlich die Lehrkraft-Rolle** — `group` allein heißt *alle Mitglieder*, also auch Schüler:innen. Der Wert kam am 24.09.2026 (Alembic 0074), weil Planungsknoten auf `group` standen und Schüler:innen damit die Stundenentwürfe ihrer Lehrkraft lesen konnten, `metadata.reflexion` eingeschlossen |
| `filters.py` | **Eine** Übersetzung der Feldfilter (Fach, Typ, Stufe, Titel …) — genutzt von der Aufzählung *und* von `GET /context/nodes` |
| `lookup.py` | Normalisierung von Titeln und Bildung des Nachschlage-Begriffs |
| `retrieval.py` | Nur noch der **Lernstand** (`node_engagement`). Er ist Traversierung, keine Suche — die frühere zweite Vektorsuche für Anker-Assistenten ist in `search.py` aufgegangen |
| `embedding.py` | Einbettung der Knoten (welche Typen, siehe `app/context/taxonomy.yaml`) |

**Die vier Verfahren** beantworten verschiedene Fragen und dürfen deshalb nicht
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
- **Vorab-Suche** (`vorab()`) — „was gehört vermutlich zu dieser Nachricht". Läuft zu
  **jeder** Chat-Nachricht, ohne dass jemand danach fragt, in **zwei Stufen** (seit 0.16):
  bis zu fünf **sichere** Treffer als Inhalt im System-Prompt (exakter Namens- oder
  Suchbegriff-Treffer, sonst Kosinus-Distanz ≤ `VORAB_SCHWELLE`), dazu bis zu fünf
  **angebotene** Titel ohne Inhalt. Deshalb die einzige, die **Schwellen** kennt.
  Beschränkt auf `VORAB_TYPEN` — die Arten, die Schüler:innen im Unterricht in die Hand
  bekommen (Flag `collection.schueler` der Taxonomie). Einzelheiten unten unter „Die
  Vorab-Suche: Zusage und Angebot"; Begründung und Messung: ADR-017, Nachträge
  „Vorab-Suche als Grundschicht" und 14.10.2026.

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
| **Grundschicht jedes Chats** | Vorab-Suche: sicher (Name/Alias + Schwelle) und Angebot (Nennung + Band) | `VORAB_MAX` = 5 Inhalte, `VORAB_ANGEBOT_MAX` = 5 Titel |

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
| `app/context/taxonomy.yaml`, `embedding: true` je content_type | Entscheidet, ob ein Knotentyp **thematisch** auffindbar ist. Ohne Embedding bleibt er über Name und Aufzählung erreichbar, taucht aber in keiner Ähnlichkeitssuche auf. Seit 09/2026: 28 von 42 Typen |
| `app/context/taxonomy.yaml`, `embedding_input` je content_type | Woraus der Vektor gebildet wird — die **einzige** Stelle, an der sich etwas gezielt weglassen lässt (Stundenentwurf: Thema statt Verlaufsplan). Ändern entwertet bestehende Vektoren dieses Typs und verlangt einen Re-Embed |
| `ROLLEN_TYP_BONUS` | `context/taxonomy.py` | Rollenabhängiger Vorsprung je Bausteinart (≤ 0,05, Bildungsplan-Typen neutral). Ein Vorzug, kein Filter — Rechte regelt `visibility.py` |
| `lookup.py`, `GENERISCHE_WOERTER` | Wörter, die bei der Begriffsbildung wegfallen („Operator", „Bedeutung", Artikel …). Betrifft **nur** den exakten Abgleich — die Teilsuche bekommt die Rohanfrage |

### Was ein Treffer dem Modell über sich sagt

**Die Auswahl liegt in `app/context/modellsicht.py`** — seit dem 26.09.2026 nicht mehr im
Chat-Router, weil zwei Wege dieselbe Entscheidung brauchen: das Suchwerkzeug und die
Vorab-Suche. Dort stehen auch die beiden Regeln, die den Text betreffen:

- **Lesehinweis** (`mit_lesehinweis`): Vor jedem Kontextblock steht
  `pedagogy.kontext_hinweis` — bevorzugte Bezeichnung statt Suchbegriff, Irrtümer nutzen
  statt aufzählen, Werte unverändert. ⚠️ Vorher standen diese Regeln nur in der
  Werkzeugbeschreibung und im Assistenten-Prompt; im freien Chat gibt es weder das eine
  noch das andere.
- **Kürzung** (`kuerze`): Für `begriff` und `stoffsteckbrief` abschnittsweise —
  Definition und Erklärung vollständig, Beispiele nach Budget (1 500 Zeichen), Schnitt
  auf einer Zeilengrenze, sichtbares „…". Alle anderen Arten behalten den harten Schnitt
  bei 800. Gemessen am Pilotbestand: Der Beispiel-Abschnitt erreichte das Modell vorher
  in 11 von 36 Fällen, jetzt in 30; die Bildplatzhalter in 2 von 5, jetzt in 4.
  **Seit 0.14 (F4) hat der Kern einen eigenen Deckel** (`INHALT_MAX_ZEICHEN_KERN`, 2 500):
  Ist er länger als das Gesamtbudget, kommt er ganz, nur ohne Beispiele. Bei 1 500
  verloren 15 von 112 Begriffen Teile ihres Kerns, darunter Antwortrelevantes („Ein
  Magnesiumbrand wird mit trockenem Sand abgedeckt"); die AP7-Kontextblöcke wuchsen durch
  den Deckel um 0,5 %. Welche Kerne betroffen sind, zeigt `scripts/kern_kuerzung.py`
  (`--text` mit dem abgeschnittenen Teil).


Nicht alles, was an einem Knoten steht, geht in den Modellkontext — und was geht, ist
beschriftet. Entschieden wird das an **einer** Stelle, `fuer_modell` in
`app/context/modellsicht.py` — für beide Wege, Vorab-Suche und Werkzeug. Leere Felder
(`None`, `""`, `[]`, `{}`) fallen dort weg (0.14, F3); bis dahin trug jeder Fachbegriff
`"nr": null` und `"bp_version": null` in den Prompt.

| Feld | Herkunft | Warum es so heißt |
|---|---|---|
| `content` | Knotentext, gekürzt mit `kuerze` (siehe oben) | Abbildungsplatzhalter werden **vor** dem Kürzen zur Beschreibung aufgelöst |
| Metadaten je Typ | `MODELL_METADATA` in `taxonomy.py` | Whitelist, kein „alles Metadata“ — die Spalte trägt auch Import-Interna und ganze SVG-Dokumente |
| `suchbegriffe` | `node_aliases` | ⚠️ **Die Beschriftung ist die Maßnahme.** Unbenannt („aliase") standen sie gleichberechtigt neben dem bevorzugten Begriff, und das Modell verwendete sie: Es antwortete „Wasserstoffbrückenbindung“, obwohl der Knoten „Wasserstoffbrücken“ heißt. Aliase sind das, **wonach gefragt wird**, auch in schiefer Form („Mol“ für die Stoffmenge) |
| `abgrenzungen` | Kanten `related_to` mit `art: abgrenzung` | Wovon sich der Knoten unterscheidet und wodurch. Höchstens fünf je Treffer, nur **aktive** Ziele, Titel statt IDs |

⚠️ **Die Abgrenzungen sind der Sonderfall unter diesen Feldern**: Sie stehen weder im
Knotentext noch im Embedding. `## Abgrenzung` bleibt aus `content` heraus — aus demselben
Grund wie die Fehlvorstellungen: Sie sagen, was der Begriff **nicht** ist, und zögen im
Vektor genau die Fragen an, die sie abgrenzen sollen. Bis 09/2026 sah das Modell sie
deshalb **gar nicht**, dabei sind es die Sätze, die Verwechslungen verhindern.

| `stufe` | Klassenstufe der Person gegen die des Knotens | Nur **wo etwas nicht passt** — „kommt ab Klasse 10“, „Vorwissen (frühere Fassung)“, „früherer Stoff“. Passende Treffer stehen ohne Vermerk vorn |

### Klassenstufe: kennzeichnen und sortieren, nicht filtern

Woher die Stufe kommt, entscheidet `stufe_der_person` (`context/service.py`) in dieser
Reihenfolge: **Unterrichtsgruppe der Konversation**, dann der Jahrgang aus der
Anmeldung. Die Gruppe gewinnt, weil sie genauer ist — eine Zehntklässlerin im Chemie-Chat
ihrer Klasse 10 ist dort in Klasse 10, auch wenn ihr Konto etwas anderes sagt.
Unbekannt bleibt unbekannt: Ein Rückfall auf eine Vorgabe behandelte jeden Erwachsenen
ohne Jahrgang wie eine Achtklässlerin.

Die Stufe eines **Bausteins** kommt aus zwei Quellen (`context/stufen.py`):

1. `metadata.ab_klasse` bei Begriffen mit mehreren Fassungen. Welche die aktuelle ist,
   entscheidet der Vergleich **untereinander** — die höchste erreichte Stufe gewinnt,
   frühere sind Vorwissen. Ohne diesen Vergleich wäre jeder Begriff unterhalb der
   Stufe „Vorwissen“, also fast jeder.
2. Sonst das Klassenband seiner Bildungsplan-Fundstellen. Es steht in den Daten
   (`min_grade`/`max_grade` an der Kompetenz) und wird nicht nachgebaut; gezählt werden
   nur **aktive** Ziele in der für Fach und Stufe geltenden Edition.

⚠️ **Gefiltert wird nicht.** Fragt eine Neuntklässlerin ausdrücklich nach der
Elektronen-Fassung der Oxidation, fände der Assistent sonst nichts und antwortete aus
dem Modellwissen — also ohne die Definition ihrer Schule. Sortiert wird **stabil** und
in zwei Gruppen (passt / passt nicht); „kommt später“ gegen „Vorwissen“ zu
ordnen hieße, eine Vorliebe zu behaupten, für die es keine Grundlage gibt.

Die **Aufzählung** kennzeichnet, sortiert aber nicht: Sie beantwortet „alle, die …“
und ist nach Fach und Titel geordnet — das ist ihre Aussage.

⚠️ **Im Embedding und im Namensabgleich bleiben Aliase unverändert** — dort sind sie
richtig. Drei Prüfsatzfälle halten das fest („Mol“, „Molzahl“,
„Wasserstoffbrückenbindung“): Wer bei der Beschriftung versehentlich die Suche
anfasst, sieht es dort.

⚠️ **Der Eigentümer-Bonus und die rollenbasierte Gewichtung hängen an derselben
Vorbedingung: Der Typ muss überhaupt ein Embedding tragen.** Ein Bonus auf etwas, das in
der thematischen Auswahl nie erscheint, tut nichts. Bis zur Embedding-Ausweitung
(ADR-017) galt das für **alle** nutzererzeugten Bausteine — Arbeitsblätter, Klausuren und
Stundenentwürfe waren dort strukturell unsichtbar, und die Gewichtung lief leer. Heute
tragen 28 der 42 Typen ein Embedding; die 14 übrigen bleiben bewusst draußen und sind
über Name und Aufzählung erreichbar. Wer daran etwas ändern will, ändert zuerst die
Taxonomie und lässt den Embedding-Backfill laufen.

---

## Die Vorab-Suche: Zusage und Angebot (0.16)

**Ein Inhalt wird geglaubt, also muss er sicher sein. Ein Titel kostet nichts, also darf er
breit sein.** Darauf beruht die Grundschicht seit 0.16 (Plan „Vorab-Suche-Begriffe" § 7,
ADR-017, Nachtrag 14.10.2026). Bis 0.15 gab es nur Inhalte, und jeder Weg, Begriffe in
Erzählsätzen zu finden („Letzte Stunde haben wir etwas über Elektronegativität gelernt …"),
brachte Alltagswörter mit herein: „Stoff", „Probe" und „Reduktion" im Alltagssinn liegen so
nah wie gewollte Nennungen. Gleichzeitig sucht gpt-oss ohne Anstoß praktisch nie selbst —
mit einem Titel im Systemtext aber in rund zwei Dritteln der Fälle.

| Stufe | Rolle | Was hineinkommt | Im Prompt |
|---|---|---|---|
| **sicher** | Zusage — darauf verlassen sich Prompt und Kontext-Zeile | Namenstreffer (`_kandidaten`); Distanz ≤ `VORAB_SCHWELLE`, im Chat mit Fach nur aus Fach, Bezugsfächern und fachlos (F8) | JSON-Block mit Lesehinweis, wie bisher |
| **Angebot** | Bestleistung — das Modell holt, was es braucht | was **nicht sicher** ist und roh ≤ `VORAB_ANGEBOT` liegt: zuerst im Satz Genanntes (`nennung.py`), dann Distanz aus denselben 15 Kandidaten — außer Knoten mit `angebot: nur wenn genannt` | ein Satz: „Im Wissensspeicher der Schule gibt es dazu/außerdem: Titel (Fach), … — den Inhalt holst du mit dem Werkzeug, wenn er für die Antwort zählt." |

| Wert | Ort | Wirkung |
|---|---|---|
| `VORAB_SCHWELLE` = 0,45 | `search.py` | Grenze der sicheren Stufe. Liegt in der Lücke von `vorab_schwelle.py` (0,433 / 0,481) — nicht verschieben, ohne neu zu messen |
| `VORAB_ANGEBOT` = 0,50 | `search.py` | Grenze des Angebots, rohe Distanz. Das Band-Raster des Prüfsatzes (0,46–0,55) zeigt, was ein breiteres Band kostete |
| `VORAB_MAX` = 5 · `VORAB_ANGEBOT_MAX` = 5 | `search.py` | Deckel je Stufe. Was der Deckel aus der sicheren Stufe drängt, fällt ins Angebot, nicht durch beide |
| `INDEX_TTL` = 60 s | `nennung.py` | Wie alt der Namensindex (Titel und Aliase im Speicher) höchstens ist; Neuaufbau rund 6 ms |

**Die Nennung** (`app/context/nennung.py`): Titel und Aliase der Vorab-Typen als Wortfolgen in
der Nachricht — an Wortgrenzen, längste zuerst, einfache Endungen auf **beiden** Seiten
(„eines Alkans" ↔ „Alkane"), keine Komposita. Im Chat mit Fach zählen Begriffe dieses Fachs,
seiner Bezugsfächer und fachlose; ohne Fach alle. Eine Nennung führt **nur zum Angebot**, nie
zum Inhalt — auch ein Alias. Genannte Knoten, die schon unter den Kandidaten stehen, kommen
aus deren Zeilen; nur fehlende holt eine kleine Zusatzabfrage.

**Bezugsfächer** (`subjects.bezugsfaecher`, aus `config/subjects.yaml` per
`seed_subjects.py`, Alembic 0085): gerichtet — „NwT liest Biologie mit" heißt nicht
umgekehrt. Sie wirken an drei Stellen: Nennung, Fachfilter der sicheren Stufe (F8) und
Verweise im Fachbegriff-Import (`docs/dev/fachbegriffe-import.md`).

**Der Fachfilter (F8)** nimmt aus der sicheren Stufe Distanztreffer aus Fächern ohne Bezug —
„schriftliche Addition" im Mathe-Chat traf sonst die Chemie-Addition (0,392). Sie fallen ins
Angebot. Namenstreffer filtert er nicht, den freien Chat auch nicht. Gemessen 15.10.2026: die
sieben Fehltreffer aus Fächern ohne Bezug fielen weg, kein erwarteter Knoten ging verloren.

**Nur wenn genannt** (Feld `angebot` an `begriff` und `stoffsteckbrief`, im Editor „Im Chat
anbieten"; `search.NUR_WENN_GENANNT`): Die Fachschaft nimmt einen Knoten aus dem Angebot über
die **Distanz**. Für Einträge, deren Thema einem Alltagsthema nahe liegt, die aber nur
fachlich gemeint sind — der Vektor trennt „die Umwelt schützen" nicht von „umweltgefährliche
Stoffe". Name, Nennung und sichere Stufe bleiben. Gemessen 15.10.2026 (Plan § 7.9, zwölf neue
Umwelt-Sätze, zwei Profile): Mit GHS09 markiert fallen alle Distanz-Angebote weg, keine
echte GHS09-Frage geht verloren. Dieselbe Sperre auch für die sichere Stufe kostete sechs von
neun echten Fragen den Inhalt („Piktogramm mit dem toten Fisch" trifft nur über die Distanz,
die Nennung scheitert an der Beugung) — deshalb nicht. Die Kandidatenzeilen tragen
`metadata` ohnehin; die Prüfung kostet keine Abfrage.

**Die Texte, die dazugehören:** Die Beschreibung von `search_context_nodes` beginnt mit der
positiven Regel („Bei Fachbegriffen, Methoden oder Operatoren aus dem Unterricht suchst du vor
der Antwort im Wissensspeicher der Schule"); der Vorrangsatz kommt als Schulkonfiguration aus
`pedagogy.yaml` (`preambles.wissensspeicher_vorrang`, optional, direkt nach der Basis).

**Was wo sichtbar ist:**
- Die Zeile „Kontext" unter der Antwort zeigt sichere Treffer (`vorab`) und
  Werkzeugergebnisse (`werkzeug`). **Angebote nicht** — sie lagen nicht vor
  (`bausteine.Angebot` ist bewusst kein Baustein). Holt das Modell eines, steht es als
  `werkzeug` da.
- **Messkanal** `vorab_debug` (SSE, **nur außerhalb der Produktion**, nicht an `is_test`
  gebunden): angebotene Knoten, welche davon im Werkzeugergebnis standen, Suchanfragen des
  Modells. Die Oberfläche ignoriert ihn; `chat_probe.py` liest ihn.
- **Statistik** `vorab_statistik` (Alembic 0086, `app/context/vorab_statistik.py`): je
  Woche, Knoten, Stufe, Fach des Chats und Modell, ohne Personenbezug; gezählt nach dem
  Speichern in eigener Transaktion, Vorschau-Chats nicht. Schlüssel `UNIQUE NULLS NOT
  DISTINCT` — ohne die Klausel legte `ON CONFLICT` für den Chat ohne Fach jedes Mal eine neue
  Zeile an. Lesen: `/statistics/vorab`, Bedeutung der Zahlen in
  `docs/admin/vorab-statistik.md`. „Nachgeschlagen" heißt: im Werkzeugergebnis derselben
  Antwort — nicht unbedingt gezielt geholt.

**Messen** — `backend/scripts/vorab_begriffe.py`:
- ohne `--chats`: der Prüfsatz gegen die echte `vorab()` — je Nachricht und Profil sichere
  Treffer (Weg Name/Distanz) und Angebot (Nennung/Distanz), Schwellen 0,40–0,52, Band-Raster
  0,46–0,55, Zeit;
- mit `--chats`: Test-Chats in vorübergehenden Messgruppen, mit Messkanal und dem Abgleich
  der Statistik (Tabelle vor und nach dem Lauf);
- Szenarien `scripts/szenarien/vorab_begriffe.yaml` und `vorab_begriffe_reihe2.yaml` (die
  zweite Reihe schrieb Jan, ungesehen beim Justieren).

Stand 15.10.2026 (Plan § 7.8, „Ergebnis Schritt 5"): sichere Stufe gleich 0.15; erwarteter
Knoten in 35/53 fachlichen Nachrichten sicher, mit nachgeschlagenen Angeboten 41–47/53;
Angebot ohne sicheren Treffer zu rund zwei Dritteln nachgeschlagen, mit sicherem daneben
fast nie.

⚠️ **Was bleibt:** Ein Titel, der die Bedeutung selbst trägt, verbiegt eine Alltagsantwort
auch ohne Suche („Das Thema können wir ausklammern." → Ausklammern). Und ein Knoten, dessen
Thema einem Alltagsthema nahe liegt, kommt über die Distanz — als Angebot („Ich will etwas
für die Umwelt tun." → Umwelt (GHS09), 0,476), manchmal sogar als Inhalt („Wie kann ich im
Alltag die Umwelt schützen?", 0,434). Gegen das Angebot hilft `nur wenn genannt`, gegen den
Inhalt nur ein anderer Titel: Er geht in den Vektor ein — „Baum und toter Fisch (GHS09)"
rückt beide Inhaltstreffer über die Schwelle (0,467 / 0,459; Plan Schritt 7, auf Dev so
eingespielt und markiert, in 24 Umwelt-Test-Chats kein GHS09 mehr). Die Statistik („oft
angeboten, nie nachgeschlagen") ist die Liste, an der man solche Titel und Aliase findet.

---

## Was die Gruppe schon hatte (0.20)

Päckchen AC (Plan „Begriffe im Schülerchat", Messung `Plaene/Messungen-0.20/`). **Eine Quelle,
zwei Verwender:**

- **Quelle** `app/planning/eingefuehrt.py` `eingefuehrte_begriffe(db, group_id, heute=)`:
  `node_engagement(relation='introduced')` der Gruppe (nachbereitet) ∪ `refs` vergangener, **nicht**
  nachbereiteter Stunden („laut Plan" — eine nachbereitete Stunde trägt ihre Begriffe über
  `introduced`, sonst kämen die `refs_offen` zurück). Nur `BEGRIFF_TYPEN`, aktiv,
  `visibility.fuer_gruppe_lesbar`. Je Begriff jüngstes Datum und Einheit.
- **Vorab-Suche:** `Suchprofil.eingefuehrt` (aus `service._eingefuehrt_in_der_gruppe`, ohne
  Horizont). Ein Angebotskandidat aus diesem Satz wird **sicher** (`grund="gruppe"`), solange
  unter `VORAB_MAX` Platz ist. Knoten mit „nur wenn genannt" bleiben Angebot. `grund` geht
  nicht ans Modell (`modellsicht.fuer_modell`), nur in Statistik (`vorab_statistik.grund`,
  Alembic 0089) und Messkanal (`vorab_debug.sicher_gruppe`).
- **Block „Aktueller Unterricht":** `student_context._bereits_eingefuehrt` — Einheit der letzten
  Stunde, sonst `EINGEFUEHRT_STUNDEN` (8); ohne die Titel der zwei Stunden; `EINGEFUEHRT_TITEL`
  (12). Die Kennungen gehen als `Kontext.block_angebot` in die Statistik (`grund="block"`, ohne
  Wochenzähler).

⚠️ **Fehltreffer beobachten, nicht wegdefinieren.** Der Stufenwechsel macht ein Alltagswort
sicher, sobald die Gruppe den Begriff hatte. Die Gegenprobe (dasselbe Wort in einer Gruppe ohne
Einführung bleibt Angebot) steht in `test_vorab_suche_db.py::TestEingefuehrtInDerGruppe`; im
Betrieb zeigt `/statistics/vorab` „davon Gruppe".

## Aliase — ein zweiter Titel, kein Metadatenfeld

Seit Migration **0057** liegen weitere Namen in der Tabelle `node_aliases`, vorher als
JSON-Liste in `metadata.aliase`. Der Umzug hat einen Grund und eine Falle.

**Der Grund:** Als Metadatenfeld trugen Aliase nur das Embedding von `methode` und
`operator`. Die **Namenssuche sah sie nie** — wer „Ich-Du-Wir" tippte, fand
„Think-Pair-Share" nicht, obwohl der Alias gepflegt war. Ein Feld, das man pflegen kann
und das nichts bewirkt.

Jetzt greift ein Alias in **allen drei Namensstufen**: exakter Abgleich, Ähnlichkeit,
Präfix-Vervollständigung. Verglichen wird über dieselbe Normalisierung wie bei Titeln —
klein, ohne Gliederungsnummer, ein Leerraum. **Bindestriche werden nicht gefaltet:**
„Think-Pair-Share" und „Think Pair Share" sind zwei Namen, genau wie bei Titeln. Diese
Lücke schließt die Ähnlichkeitsstufe, nicht die Normalisierung; hätte sie eine eigene
Regel, verhielten sich Aliase anders als Titel.

⚠️ **Die Falle: kein `EXISTS` in der Hauptabfrage.** Der naheliegende Weg — ein
korreliertes `EXISTS` per `OR` an die Identifikation — ist fachlich richtig und macht
aus dem Index-Scan auf dem Titelausdruck einen vollständigen Durchlauf. Ein `OR` über
zwei Tabellen kostet den Plan. Stattdessen löst `knoten_mit_alias()` die Treffer in einer
eigenen, kurzen Abfrage auf, und die Hauptabfrage bekommt eine **ID-Liste**. Gibt es
keine Aliastreffer — der Normalfall —, ist die Bedingung zeichengleich zu vorher.

Das ist genau der stille Ausfall, vor dem der Abschnitt *Indexe* warnt; gefangen hat ihn
der `EXPLAIN`-Test, nicht das Auge.

**Sortierung:** In der Ähnlichkeitsstufe entscheidet `greatest(Titel-Ähnlichkeit, beste
Alias-Ähnlichkeit)`. Ohne das stünde ein Knoten, der nur über seinen Alias trifft, hinter
jedem schwachen Titeltreffer.

**Reihenfolge ist Teil der Daten.** Bei `methode` und `operator` gehen die Aliase in den
Embedding-Input ein (`embedding_input: [… "aliases" …]` bzw. der Operator-Sonderweg).
Eine andere Reihenfolge ergäbe einen anderen Eingabetext und damit Vektoren, die mit den
bestehenden nicht mehr vergleichbar sind. Deshalb hat `node_aliases` eine aufsteigende
`id` statt einer UUID, und überall wird danach sortiert — nie alphabetisch. Aus demselben
Grund verbindet die Quelle `aliases` mit `" | "` und nicht mit `", "`: So verband der
alte Metadaten-Weg eine Liste.

Gelesen und geschrieben wird ausschließlich über `app/context/aliase.py`. **Eine
Ausnahme:** Der Bildungsplan-Import (`scripts/import_bildungsplan.py`) schreibt die
Operator-Synonyme mit reinem SQL, weil er auch ohne `app`-Paket laufen soll. Er
**ergänzt** nur, damit im Editor nachgetragene Namen einen Neu-Import überstehen.

⚠️ **`metadata.aliase` ist tot.** Bis 0.13.0 schrieben Import, Methodik-Seed und
`POST/PATCH /context/nodes` weiter dorthin — ohne Fehler und ohne Wirkung, weil seit
0057 niemand das Feld liest; der Namensfilter `?q=` las es als Einziger noch. Seit 0.13.1
weist `validate_node_metadata` das Feld ab, und `scripts/aliase_nachziehen.py` holt
einmal nach, was bis dahin dort gelandet ist.

---

## Die Bausteine einer Antwort (0.14)

Zu jeder Assistenten-Nachricht hält `message_context_nodes` fest, welche Bausteine beim
Antworten **vorlagen** — nicht, welche das Modell benutzt hat; das weiß nur das Modell.
Deshalb heißt die Zeile darunter „Kontext", nicht „Quellen".

- **Zwei Herkünfte:** `vorab` sind die Treffer der Grundschicht, also **dieselben**, die in
  den Prompt gehen (`_grundschicht` liefert beides aus einer Trefferliste); `werkzeug` ist,
  was `search_context_nodes` und `list_context_nodes` dem Modell zusätzlich geliefert
  haben. Die Werkzeuge hängen es an einen Sammler am `ToolContext` — eine Liste je Anfrage,
  weil der `ToolContext` je Aufruf neu entsteht.
- **Nicht dabei:** Ankerkontext, angeheftete Knoten, Lernstand (`app/context/bausteine.py`)
  — und das **Angebot** der Vorab-Suche (0.16): Dort stand nur ein Titel.
- **Reihenfolge des ersten Auftretens**, jeder Knoten einmal; was vorab da war, bleibt
  `vorab`.
- **Ähnlichkeit** (1 − Kosinusdistanz) nur bei thematischen Vorab-Treffern. Die Distanz
  reist dafür am Treffer mit (`distanz`) und wird in `fuer_modell` **abgestreift** — sonst
  stünde sie im Prompt. Ob der Prompt nach einer solchen Änderung zeichengleich bleibt,
  zeigt `scripts/kontextblock.py` per `diff`.
- **Gespeichert im selben Commit wie die Nachricht** (`_persist`), nur für Knoten, die es
  dann noch gibt — ein in der Zwischenzeit gelöschter Baustein darf die Antwort nicht
  mitreißen. Löschkaskade an Nachricht und Knoten.

`get_context_for_query` liefert weiter nur den Text; den Text **und** die Bausteine liefert
`kontext_fuer_frage`.

**Die Zeile unter der Antwort** liest die Liste mit `kontext_der_nachrichten` — live wie
nach dem Neuladen **dieselbe** Abfrage: Der Stream schickt nach dem Speichern das Ereignis
`kontext` (vor `message`), `GET /conversations/{id}/messages` trägt dasselbe als
`message.kontext`. Was der Stream zeigt, kann so nach dem Neuladen nicht fehlen.

- ⚠️ **Sichtbarkeit beim Lesen erneut geprüft** (`read_scope_clause`): Ein Baustein, der
  inzwischen privat ist oder einer Gruppe gehört, aus der die Person ausgetreten ist,
  verschwindet aus der Liste. `updated_at` ist der **heutige** Stand des Knotens.
- **Keine leere Zeile:** Ohne Bausteine gibt es kein Ereignis und keine Zeile — auch nicht,
  wenn alle Bausteine seitdem gelöscht oder unlesbar sind.
- Wie ausführlich, entscheidet `preferences.kontext_anzeige` (`aus` | `kurz` |
  `ausfuehrlich`, Vorgabe `kurz`) allein im Frontend (`$lib/kontext_anzeige.js`).
  `ausfuehrlich` ist zugleich das Diagnosewerkzeug für die Vorab-Suche: Fundweg (vorab /
  vom Assistenten nachgeschlagen), Ähnlichkeit oder „über den Namen".
- **Abbildungen** (nur `ausfuehrlich`): Die Liste trägt nur `hat_abbildungen`; die SVGs
  holt die Oberfläche erst beim Aufklappen über `GET /context/nodes/{id}`, einmal je
  Knoten und Seitenaufruf (`ladeAbbildungen`). Mitgeschickt wöge eine Konversation beim
  Neuladen schnell Megabytes — ein Knoten mit Abbildungen trägt im Mittel 36 KB SVG, bis
  126 KB (Dev, 07.10.2026). Gesetzt werden sie von `fuelleAbbildungen`, also sanitisiert wie
  in der Detailansicht; welche Abbildungen ein Knoten hat (Illustrationen, beim Bauteil das
  Schaltzeichen), sagt `alleAbbildungen` in `$lib/abbildungen.js` — dieselbe Regel steht als
  SQL in `bausteine._HAT_ABBILDUNGEN`.

---

## Warum der `@`-Weg anders ist

Der `@`-Shortcode im Chat ist **Namensvervollständigung**, nicht Suche: Man tippt einen
Titel, den man kennt. Zwei Abweichungen folgen daraus, beide gemessen am 01.09.2026.

**Keine thematische Auswahl** (`identification_only`). Sie kostet einen Netzaufruf zum
Embedding-Modell — rund 370 ms, über den Systemschlüssel aufs Systemkonto. Das Dropdown fragt
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

## „Meine Bausteine" — was „eigen" heißt, und wer was darf

`/knowledge/mine` (Abfrageschicht: `app/context/meine_bausteine.py`) ist die einzige
Wissensgraph-Fläche, die **allen Rollen** offensteht. Zwei Entscheidungen dahinter sind
nicht offensichtlich.

### Der Bestand: Pseudonym **und** Typ

Gefiltert wird nicht nur nach `owner_pseudonym`. Das Pseudonym steht auch auf Dingen,
die niemandem einzeln gehören — ein Curriculum beschließt die Fachschaft gemeinsam, das
Änderungsrecht liegt bei `write_scope = subject`; das Pseudonym daran ist
**Urheberschaft, nicht Eigentum**. Solche Knoten auf einer persönlichen Seite zu führen
(und dort zur Aufmerksamkeit zu mahnen) legte eine Zuständigkeit nahe, die es nicht gibt.

Die Typmenge dafür ist **abgeleitet, nicht gepflegt**:
`PERSOENLICHE_CONTENT_TYPES` in `taxonomy.py` ist genau die Menge mit
`scope_defaults.write_scope == "private"` — 16 von 42 Typen, deckungsgleich mit
Lehrkraft-Material, Lehrkraft-Planung und Schüler-Artefakten.

⚠️ **Der Vorgabewert des Typs, nicht der Scope des Knotens.** Letzterer ist eine
Nutzerentscheidung — das Anlegeformular bietet `private`/`group`/`subject` zur Wahl — und
beantwortet „wer darf diesen einen bearbeiten", nicht „was für ein Ding ist das". Wer
sein Arbeitsblatt mit der Fachschaft teilt, verlöre es sonst von der eigenen Seite; ein
privat gesetzter Fachbegriff erschiene dort fälschlich.

### Die Rechte: Rollenriegel gefallen, Rechteriegel nicht

Vier Endpunkte sind rollenoffen (`get_current_user` statt `_TEACHER_OR_ADMIN`):
`GET /nodes/{id}`, `POST /nodes/{id}/reaktivieren`, `DELETE /nodes/{id}` und
`PATCH /nodes/{id}/verwalten`. Abgesichert sind sie durch `_check_read_permission` bzw.
`_check_write_permission` — beide rollenblind und im Zweifel strenger: eigene Knoten
immer, `private` von Fremden nie (auch für Admins nicht), `group` nur mit
Mitgliedschaft.

Der Grund für die Öffnung ist Konsistenz, nicht Bequemlichkeit: **Dieselbe Knotenmenge
liefert die Suche Schüler:innen ohnehin schon.** Dass ausgerechnet die Detailansicht
403 gab, war die Unstimmigkeit.

⚠️ **`PATCH /nodes/{id}/verwalten` ist bewusst schmal** — `title`, `status`,
`valid_until`, sonst nichts. Der generische `PATCH /nodes/{id}` bleibt teacher/admin. Ihn
zu öffnen hätte auch Scopes, Inhalt und Metadaten freigegeben; ein versehentlich auf
`school` gestelltes `read_scope` veröffentlicht einen Text, den jemand für sich
geschrieben hat. Das ist Leitprinzip 5 der UI-Notiz von der technischen Seite:
*Verwalten ist nicht Bearbeiten.*

`valid_until` braucht dabei das Begleitflag `valid_until_gesetzt`: Ohne es ließe sich
„auf `null` setzen" (= gilt dauerhaft) nicht von „Feld weggelassen" unterscheiden.

### „Eingesetzt in": zwei Kantenrichtungen, eine Frage

- **Material** trägt *eingehende* `used_with`-Kanten von den Stunden, die es benutzen
  (siehe Abschnitt unten).
- **Planungsknoten** hängen andersherum: Eine Stunde zeigt per *ausgehendem* `part_of`
  auf ihre Einheit, die Einheit auf ihren Jahresplan.

Beides beantwortet „wo steckt das drin?", deshalb eine Funktion und ein Feld — aber zwei
Abfragen, gesammelt für alle Knoten auf einmal. Je Knoten wären es bei 200 eigenen
Bausteinen 400 Rundreisen.

---

## Materialkanten — der Rückweg von der Stunde zum Baustein

Keine Suche, sondern Traversierung: die Frage „**wo** wird dieser Baustein eingesetzt?"
— und damit „kann ich ihn gefahrlos ändern oder löschen?". Sie steht hier, weil sie
sonst mit der thematischen Auswahl verwechselt wird; Embeddings sind daran unbeteiligt.

Eine Stunde führt ihr Material **je Phase** in `metadata.phasen[].material[]`, jeder
Eintrag entweder Freitext oder eine Knotenreferenz (`LessonLinkedItem`:
`{typ: "text"|"node", wert, node_id, titel}`). Die Phase ist der richtige Ort dafür —
ein Arbeitsblatt gehört zur Erarbeitung, nicht zur ganzen Stunde. Für den Rückweg taugt
das nicht: Man müsste alle Stunden der Schule durchsehen.

Deshalb entsteht beim Speichern zusätzlich eine **`used_with`-Kante von der Stunde auf
den Baustein**, mit den Phasen als Angabe an der Kante
(`{"via": "material", "phasen": [...]}`). Die Ableitung liegt in
`app/planning/material_edges.py`; dasselbe Muster nutzt der Curriculum-Editor
(`context/service.py`, Material-Token → `used_with`).

### Die Regel: Abhängigkeit, nicht Nennung

| Feld einer Phase | Kante? | Warum |
|---|---|---|
| `material[]` | **ja** | Inhalt, den die Stunde benutzt. Verschwindet er, fehlt er |
| `methode` | nein | Beschreibt die Phase. `LessonLinkedItem` hält `titel` redundant — verschwindet der Knoten „Gruppenpuzzle", steht in der Stunde weiterhin „Gruppenpuzzle" |
| `sozialform` | nein | wie `methode` |

Die Regel ist **am Feld ablesbar** und braucht keine Typprüfung: `material` ist eine
Liste von Inhalten, `methode`/`sozialform` sind beschreibende Einzelfelder. Sie gilt auch
für Ziele, die niemandem persönlich gehören — ein `begriff` der Fachschaft kann ebenso
geändert oder archiviert werden.

⚠️ **Methoden und Sozialformen zu verkanten wäre aktiv schädlich**, nicht nur überflüssig:
Die Aufmerksamkeits-Warnung in „Meine Bausteine" zählt archivierte Referenzen — archiviert
jemand eine Sozialform, meldeten sich schlagartig hunderte Stunden. Und im Graphen würden
zwanzig Vokabelknoten mit je hunderten Kanten zu Naben, die alles Interessante überdecken.

Bleibt die Frage „welche Methoden nutzen wir tatsächlich?", ist das eine JSONB-Abfrage
über `phasen[].methode.node_id` — dafür braucht es keine Kanten, und man baut sie, wenn
die Frage gestellt wird.

Welche Typen überhaupt als Material wählbar sind, leitet
`frontend/src/lib/material.js` aus der Taxonomie ab: alle Dokument-, Artefakt- und
Konzepttypen außer `unterrichtsstunde`, `unterrichtseinheit`, `schuelertext`,
`schuelerpraesentation`, `feedback_text`.

### Abgeleiteter Index, kein zweiter Speicherort

Die Phasen sind die Wahrheit; die Kante wird bei jedem Speichern neu daraus bestimmt.

⚠️ **Der Abgleich muss löschen, nicht nur anlegen.** `create_edge` in
`context/service.py` ist über `(from, to, relation)` idempotent — es legt keine Dublette
an, entfernt aber nichts. Wer nur anlegt, hinterlässt beim Herausnehmen von Material eine
Kante, die einen Einsatz behauptet, den es nicht mehr gibt.

⚠️ **`via: "material"` grenzt den Abgleich ein.** Ohne die Marke fasste er auch von Hand
gezogene `used_with`-Verbindungen an und löschte sie beim nächsten Speichern.

Dasselbe Material in zwei Phasen ergibt **eine** Kante mit zwei Phasen in den Metadaten —
nicht zwei Kanten. Wegen der Idempotenz fiele die zweite ohnehin stumm unter den Tisch.

**Aufgerufen wird an jeder Stelle, die Phasen schreibt** — Editor (`planning/router.py`),
Planungsassistent (`assistant_tools.py`), Verschiebe-/Übertragungslogik (`operations.py`,
für *alle* beteiligten Stunden: eine Übertragung betrifft zwei Knoten) und der
Snapshot-Rückweg (`snapshots.py`). `review_service.py` ist ausgenommen: Es setzt nur den
Phasen-Status. Ein Unit-Test wacht darüber, dass keine neue Schreibstelle den Aufruf
vergisst (`test_material_edges_abdeckung.py`) — die Vorlage dafür ist die
`valid_until`-Vorbelegung, die gebaut war, an fünf Anlegestellen keinen Eingang hatte und
deshalb bei **null von 19 134 Knoten** wirkte.

### Phasen-Kennungen

`LessonPhaseItem.id` ist `Optional`, aber es hängt mehr daran, als der Typ verrät:
`phasen_status` schlüsselt danach, die Phasen-Übertragung wählt darüber aus, und die
Materialkanten vermerken sie. Fehlt sie, fällt nichts aus — es wird still ungenau.

Sie wird deshalb **beim Speichern** vergeben (`app/planning/phasen.py`), nicht in der
Oberfläche: Der Planungsassistent schreibt Roh-Dicts aus den Werkzeug-Argumenten und geht
nicht durch `LessonPhaseItem`. Vorhandene Kennungen bleiben unangetastet — sie neu zu
vergeben zerschnitte genau die Verweise, um die es geht.

⚠️ **Im Frontend kommt es auf die Reihenfolge des Spreads an.** Bis 09/2026 stand in der
Stundenseite `{ id: p.id ?? crypto.randomUUID(), ...p }`. Bringt der Server eine Phase
mit `id: null` mit — und das tut er, `patch_lesson` speichert mit
`model_dump(exclude_none=False)` —, überschreibt der Spread die eben erzeugte Kennung
wieder mit `null`. Nur wenn der Schlüssel ganz fehlte, überlebte sie. Der Fehler ist
selbsterhaltend: Jedes Laden verwirft die neue Kennung, jedes Speichern schreibt `null`
zurück. Jetzt als `mitPhasenKennungen()` in `frontend/src/lib/planner.js`, mit Test.

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

Voraussetzungen: importierter Bildungsplan, **vollständige Vektoren** (siehe *Messfalle*
unten — das Skript prüft es selbst und bricht sonst ab), laufender LiteLLM-Proxy (für das
Embedding der Anfragen), und für die S2-Fälle die Testknoten:

```bash
python scripts/seed_search_eval_nodes.py            # anlegen
python scripts/seed_search_eval_nodes.py --entfernen # wieder wegräumen
```

Der Prüfsatz (`config/search_eval.yaml`) misst drei Frageklassen und beendet sich mit
Exit-Code 1, wenn eine Zusage bricht:

| Kennzahl | Bedeutung | Stand 27.09.2026 |
|---|---|---|
| Richtiges Fach auf Platz 1 | Rangqualität der thematischen Auswahl | 30/35 |
| Erwarteter Knoten gefunden | Wird der gesuchte Baustein überhaupt geliefert | 51/54 (mittlerer Rang 2,1) |
| Recall@10 | Wächter gegen einen wiederkehrenden Vektorindex | 100 % |
| Aufzählungen wie erwartet | Zählung und Fächerzahl der Filterabfrage | 2/2 |
| Anker-Fälle (`anker:`) | Suche im Teilgraphen eines Assistenten | 3/3, zwei davon auf Rang 1 |
| Deckel `IDENT_DECKEL` = 3 | Wie viele Namensträger ein **thematischer** Fall höchstens erzeugen darf — thematisch heißt: mit `fach:` und **ohne** einen Knoten beim Namen zu nennen (`ist_thematisch`) | 8 solcher Fälle, größter Abschnitt 3 |

⚠️ **Die drei roten Fälle sind Altbestand** und kein Rückschritt: zweimal Deutsch
`3.4.1.1` (einmal mit, einmal ohne Fachbezug) und Informatik `3.1.2(1)`. Beide Knoten
gibt es; sie werden von ähnlicheren verdrängt. Wer daran arbeitet, prüft zuerst, ob die
Erwartung stimmt — der Bericht sagt das bei jedem Fall dazu.

**Nachgemessen 06.10.2026** (107 Fachbegriffe statt 36, vollständige Vektoren): 30/35 ·
**50/54** · 100 % · 2/2 · Deckel **gerissen**. Neu rot: „Was passiert, wenn man Säure und
Lauge mischt?" findet die Neutralisation nicht mehr; der Deckel reißt bei
„Elektronenpaarbindung" (4 Namensträger). Beides in `Todo.md`, nicht untersucht.

**Untersucht 07.10.2026:** Beides ist kein Fehler der Suche. Die **Neutralisation** steht
auf Platz 16 (Distanz 0,546) — „Lauge" kommt weder in ihrem Text noch in ihren
Suchbegriffen vor; das ergänzt die Fachschaft im Vault. Der **Deckel** riss an einer
Fehleinordnung des Prüfsatzes: „Elektronenpaarbindung", „Oxidation" und „Energie" nennen
einen Knoten beim Namen, galten aber als thematisch, weil sie ein Fach tragen. Seitdem
zählt nur als thematisch, wo kein Namensträger genau den Begriff trägt, den die
Suchschicht aus der Frage liest (`nachschlage_begriff`). Ergebnis: 5 thematische Fälle,
größter Abschnitt 2 — Exit-Code 0. Nach dem Suchbegriff „Lauge" an der Neutralisation
(Vault, 07.10.): **51/54**, die Neutralisation auf Rang 3. Rot sind wieder nur die drei
Fälle aus dem Altbestand (Deutsch `3.4.1.1` zweimal, Informatik `3.1.2(1)`).

**Für Änderungen am Prompt-Inhalt der Vorab-Suche** gibt es ein zweites Werkzeug:
`scripts/kontextblock.py` zeigt den Kontextblock, den eine Frage in den Prompt bringt —
ohne Modell, deterministisch, in einer Konversation im angegebenen Fach, die am Ende
zurückgerollt wird. Ein `diff` zweier Ausgabeverzeichnisse zeigt genau, was sich am Prompt
geändert hat; was das Modell daraus macht, misst `chat_probe.py`.

```bash
python scripts/kontextblock.py --datei scripts/szenarien/ap7_chemie.txt \
    --fach CH --stufe 8 --ausgabe /tmp/vorher
```

Mit `--gruppe` statt `--fach` misst es dieselbe Lage wie `chat_probe.py --gruppe`: Fach und
Stufe kommen dann aus der Gruppe. Die Testassistenten auf Dev sind an Unterrichtsgruppen
gebunden; `chat_probe` braucht dafür eine Schülerin, die dort Mitglied ist (`--pseudonym`).

### `typ:` — warum ein Fall ohne ihn lügen kann

Ein Fall nennt in `knoten:` den erwarteten Baustein, und `_rang` vergleicht das als
**Teilzeichenkette** gegen den Titel. Das genügt für Bildungsplan-Nummern
(`3.2.1.3`), ist aber gefährlich, sobald ein Fall einen **Fachbegriff** erwartet: Der
Bildungsplan nennt die Begriffe beim Namen. „Wasserstoffbrücken" steht auch in
„3.2.1.3(10) die besonderen Eigenschaften von Wasser erklären (Dipol,
Wasserstoffbrücken)" — der Fall wäre grün, ohne dass der Fachbegriff existiert.

⚠️ **Gemessen am 26.09.2026: Zehn von dreizehn** neu angelegten Fachbegriff-Fällen waren
so auch ohne den Pilotbestand erfüllbar. Sie waren nicht falsch, aber sie belegten
nichts.

Deshalb trägt ein Fall, der einen bestimmten Knotentyp meint, ihn ausdrücklich:

```yaml
  - frage: Wie heißt die Bindung im Wassermolekül richtig?
    fach: Chemie
    knoten: Elektronenpaarbindung
    typ: begriff          # ohne diese Zeile zählte auch die BP-Kompetenz als Treffer
```

**Der Lader weist unbekannte Schlüssel ab.** Das ist keine Kosmetik: Die erste Fassung
bildete die Felder einzeln ab und verschluckte `typ` stillschweigend — die Messung zeigte
dieselbe Zahl wie ohne, und der Fehler wäre nicht aufgefallen, hätte die Zahl nicht
*gleich* bleiben müssen.

**Unterschreiten ist ein Fehlschlag, kein Kompromiss.** Wer eine Kennzahl bewusst
opfert, begründet das im Code-Kommentar neben dem geänderten Wert — so wie es die
bestehenden Konstanten vormachen.

**Der Abschnitt S8 misst die Beschreibungen selbst, nicht die Suchschicht.** „Methoden
thematisch finden, ohne den Namen zu kennen" fragt Methoden über ihren Ablauf ab
(„Erst allein nachdenken, dann zu zweit austauschen …" → Think-Pair-Share). Fällt einer
dieser Fälle, liegt es an der Kurzbeschreibung des Knotens (`scripts/seed_methodik.py`),
nicht an der Suche — ohne Beschreibung ist der Knoten als `unvollstaendig` markiert und
hat gar keinen Vektor.

Bei `methode` bildet sich der Vektor aus dem **Ablaufsatz** (`metadata.ablauf`), nicht aus
der ganzen Kurzbeschreibung — ein Feld für Lesende, ein Satz für die Suche. Zwei Regeln
dafür, beide gemessen:

⚠️ **Kein Beiwerk.** Was einen Eintrag für Lesende reicher macht, macht seinen Vektor
unschärfer. Ein ergänzter Variantensatz („ein Gruppenmitglied bleibt stehen und erklärt es
den Besuchern") warf den Galeriegang von Rang 1 auf 7, verdrängt von den Operatoren
*präsentieren*, *demonstrieren*, *erbringen*. Genau deshalb gibt es das eigene Feld.

⚠️ **Positiv beschreiben, nicht abgrenzen.** Ein Satz wie „Anders als beim Lernzirkel
gibt es keine feste Reihenfolge" trägt den fremden Namen und den verneinten Begriff in
die Eingabe und zieht den Knoten an den heran, von dem er sich abgrenzen soll —
Verneinungen kennt ein Embedding nicht. Am S8-Fall zum Stationenlernen kostete das den
ersten Platz (Lernzirkel 0,733 gegen 0,701).

### Wo die Zeit hingeht

Gemessen am Entwicklungsbestand (01.09.2026, LiteLLM lokal):

| Schritt | Dauer |
|---|---:|
| **Embedding der Anfrage** (Netzaufruf zum Modell) | **~370 ms** |
| Identifikation (exakter Abgleich + Trigramm) | ~50 ms |
| Thematische Auswahl (nur Datenbank) | ~30 ms |
| Aufzählung | ~15 ms |
| Vorab-Suche ohne Embedding (0.16, beide Stufen) | ~7–10 ms; mit Nennung +1–2 % |

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

⚠️ **Die zweite Messfalle: fehlende Vektoren.** Am 06.10.2026 zeigte `vorab_schwelle.py`
eine scheinbar zerbrochene Schwelle — drei von sechs Fachfragen über 0,45, „Was ist eine
Oxidation?" fand den Begriff Oxidation gar nicht. Auf Dev hatten seit einem Neuimport
100 von 107 Begriffen keinen Vektor; Dev hat keinen nächtlichen Backfill. Gemessen war der
Zustand der Vektoren, nicht die Suche. Seitdem prüfen `search_eval.py`,
`vorab_schwelle.py`, `kontextblock.py` und `chat_probe.py` zuerst
(`embedding.vor_einer_messung`) und brechen mit Exit-Code 2 ab, solange Knoten fehlen;
`--trotzdem` übergeht das. „Fehlend" heißt dasselbe wie für den Backfill
(`einbettungstext`): Ein Knoten, der nur seinen Titel trüge, bekommt absichtlich keinen
Vektor und zählt nicht.

**Die Schwelle nachmessen** ist ein Aufruf: `vorab_schwelle.py` gibt am Ende den größten
erwünschten und den kleinsten unerwünschten Abstand aus, die Lücke dazwischen und ob
`VORAB_SCHWELLE` darin liegt — wenn nicht, mit Exit-Code 1. Fälle, in denen ein Treffer
richtig wäre, die aber keine Schwelle trennt (das Goethe-Gedicht), stehen gesondert als
Grenzfall und zählen zu keiner Grenze. Stand 06.10.2026: 0,433 gegen 0,481, Lücke 0,048
— wie am 26.09., bei dreimal so vielen Begriffen. Die Tabelle steht am Kommentar der
Konstanten.

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
| `idx_node_aliases_norm` | 0057 | Exakter Alias-Abgleich |
| `idx_node_aliases_trigramm` | 0057 | Teilsuche über Aliase |
| `uq_node_aliases_node_norm` | 0057 | Ein Alias je Knoten nur einmal |

Alle liegen auf **demselben** normalisierten Ausdruck — für Titel wie für Aliase —, und
alle beziehen ihn aus derselben Funktion wie die Abfrage:
`app.context.lookup.titel_normalisiert_sql`.

⚠️ Weicht der Ausdruck des Index auch nur in einem Zeichen von dem der Abfrage ab,
benutzt PostgreSQL ihn **nicht** — ohne Fehler, ohne Warnung, nur langsamer. Deshalb wird
er nie abgeschrieben, und Integrationstests prüfen die Passung
(`test_chat_context_nodes.py`). Ob der Planer den Index dann auch *wählt*, hängt an der
Tabellengröße: Auf einer fast leeren Testdatenbank tut er es nicht, auf dem
Entwicklungsbestand nachweislich.

Auf `embedding` liegt **absichtlich kein Index** (siehe oben).
