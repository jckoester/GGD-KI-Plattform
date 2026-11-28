# Vernetzung der Fächer (seit 0.66, Übersicht seit 0.67)

Päckchen BE. Plan `Plaene/Vernetzung-Zeitachse-BE-Plan.md` (F1–F14), Messungen in
`Plaene/Messungen-Vernetzung/`. Nur für Lehrkräfte, nur lesend. Zwei Teile:
- **Teil A (0.66):** eine Zeitachse über die Klassenstufen mit einem Fach in der Mitte und den
  vernetzten Fächern als Spuren.
- **Teil B (0.67):** die Übersicht Fach × Fach je Klassenstufe als Einstieg in die Zeitachse.

## Überblick

| Teil | Ort |
|---|---|
| Dienst | `app/context/vernetzung.py` — `vernetzung(db, user, fach_id, *, modus, schuljahr, bezugsstufe, entwuerfe)`, `matrix(db, user, stufe, *, schuljahr, entwuerfe)`; gemeinsam `_welt` und `_bezuege` |
| Zeit (rein) | `app/context/vernetzung_zeit.py` — Schuljahr je Stufe, Lage aus Plänen ohne Kalender, Schätzung, `als_spanne` |
| Endpunkte | `app/context/vernetzung_router.py` — `GET /context/vernetzung`, `GET /context/vernetzung/matrix`, `POST /context/vernetzung/pdf` |
| PDF | `app/context/vernetzung_export.py`, Vorlage `templates/vernetzung_pdf.html` |
| Anordnung (rein) | `frontend/src/lib/zeitachse.js` — Achse, Spuren, Spalten, Blöcke, Kurven, Klammern, Liste, Adresse |
| PDF-Zeichnung (rein) | `frontend/src/lib/zeitachse_svg.js` — je Stufe ein SVG, `pdfAnfrage()` |
| Übersicht (rein) | `frontend/src/lib/vernetzung_matrix.js` — Stärke, Kurzform, Satz, symmetrische Tabelle |
| Ansicht | `routes/(app)/knowledge/connections/+page.svelte`, `VernetzungZeitachse.svelte`, `VernetzungTafel.svelte`, `VernetzungListe.svelte`, `VernetzungMatrix.svelte` |
| Testwelt | `backend/scripts/vernetzung_testwelt.py` (nur Dev) |

`lib/vernetzung.js` ist etwas anderes: die Nachbarschaft eines Bausteins als Liste.

## Dienst

**Stufen und Fassung (F2, F13):**
- Die Stufen sind alle, die ein Curriculum des Fachs umfasst. Jede Stufe bekommt ihr Schuljahr (`vernetzung_zeit.schuljahre`): `schuljahr` für alle Stufen dasselbe, `weg` für Stufe s das laufende Jahr + (s − Bezugsstufe).
- Je Fach und Stufe gilt die Fassung `editions.aktive_bp_version(stufe, verfügbare Fassungen, Schuljahr)`. Ohne diese Regel stünden im Übergangsjahr zwei Curricula für Kl. 8 übereinander (V2 und V3).
- `_waehlen`: Ein Entwurf mit `kopie_von` ersetzt sein Original. Je Band gewinnt der Entwurf.
- Leserecht wie die Leitlinien-Übersicht: offener `read_scope`, Entwürfe nur mit `darf_entwurf_lesen` (Eintrag im Wächter `test_entwurf_leserecht_waechter.py`).

**Lage (F3):**
- Je Fach und Stufe gilt der Jahresverlaufsplan des Schuljahrs der Stufe: beschlossen vor Entwurf, archivierte vergangener Jahre eingeschlossen.
- `plan_lagen` zählt die Wochen der Abschnitte ohne Kalender. Kapitel im Plan, die ersetzt wurden, werden über `nachfolger_der_kapitel` abgebildet; ein Entwurf übernimmt die Lage seines Originals.
- Ohne Plan schätzt `schaetzen`: Stunden ÷ Wochenstunden aus `rahmen.wochenstunden`, sonst gleich verteilt. Ein Curriculum über zwei Stufen wird der Reihe nach gefüllt. Anfang und Ende werden gleich gerundet, damit sich Nachbarn keine Woche teilen.
- Die Zeitprüfung der Absprachen (`absprachen.pruefung_dict`) nimmt geschätzte Lagen nur als Stufen (`als_spanne`), sie beweisen keine Verletzung.

**Kalender:** Je Schuljahr `kalender_fuer`. Fehlt die Datei, leiht sich der Dienst die Zahl der Wochen vom laufenden Jahr und liefert keine Kalenderwochen.

**Bezüge (F1):**
- Die Kompetenzen eines Kapitels sind die Ziele der Kanten `references` seiner Lernsequenzen, getrennt nach Fach.
  - Eigene Kompetenzen sind Quellen der Querverweise.
  - Fremde Kompetenzen stammen aus `#[…](ik:…)` in den Hinweisen und zählen als Verweis.
- `related_to` gilt in beide Richtungen. Archivierte Ziele werden über `querverweise._umlenken` auf die aktive Fassung umgelenkt.
- Ein Bereich (`leitidee`) wird über `_bereich_kompetenzen` aufgelöst und ergibt `bereich`.
- Benachbarte Kapitel desselben Curriculums zählen im eigenen Fach nicht.
- Geliefert werden nur Bezüge mit dem Fach in der Mitte, je Paar mit bis zu drei Nummernpaaren als Beispiel.
- Absprachen kommen aus `metadata.absprachen` der Kapitel:
  - Ziele werden abgebildet wie bei den Plänen.
  - Absprache und Gegenabsprache werden zu einer mit `beidseitig` zusammengefasst.
  - Absprachen an das ganze Fach oder auf Kapitel außerhalb der Ansicht stehen in `fach_absprachen`.

**Spuren:** `faecher` sind die Fächer mit Bezug zur Mitte, sortiert nach Absprachen, dann
Kompetenz-, dann Bereich-Bezügen. `nur_bereich` kennzeichnet Fächer, die nur über ganze Bereiche
verbunden sind.

**Leitperspektiven, Leitlinien (F6):** nur für Kapitel der Mitte, aus `references` auf
`leitperspektive*`, `lfdb_*` und `leitbild*`. Aspekte werden über `verweisziele` zu ihrer
Leitperspektive bzw. Leitlinie zusammengefasst.

**Gemeinsamer Kern:** `_welt` liefert für Stufen und ihre Schuljahre die Curricula der geltenden
Fassung, Kapitel und Lage. `_bezuege` liefert die Bezüge, mit Fach in der Mitte (Zeitachse) oder
ohne (Matrix).

**Matrix (Teil B):**
- Kapitel zählen zu der Stufe, in der sie laut Plan oder Schätzung liegen; Kapitel ohne Lage zählen mit. Ein Bezug von Kl. 7 nach Kl. 8 erscheint deshalb in keiner Matrix.
- Je Fächerpaar (`a` ≤ `b`): `absprachen`, `verletzt`, `kompetenz`, `bereich` und `ganzes_fach` (Absprachen an das ganze Fach). Die Diagonale zählt die Bezüge im eigenen Fach.
- `stufen`: alle Stufen mit lesbarem Curriculum, für die Wahl der Stufe.
- Gemessen mit der Testwelt: rund 100–135 ms, rund 4 KB.

Die eigene Variante der Querverweise ist nötig, weil `querverweise()` Bezüge im eigenen Fach
ausdrücklich übergeht. Gemessen mit der Testwelt: 180–380 ms, bis 77 KB je Antwort.

## Endpunkte

- `GET /context/vernetzung?fach=&schuljahr=&weg=&entwuerfe=` — `fach` als Kürzel (Groß- und
  Kleinschreibung egal) oder Kennung. `schuljahr` und `weg` schließen sich aus (422). Nur
  `teacher`/`admin`.
- `GET /context/vernetzung/matrix?stufe=&schuljahr=&entwuerfe=` — `stufe` Pflicht. Nur
  `teacher`/`admin`.
- `POST /context/vernetzung/pdf` — die Anfrage aus `pdfAnfrage()`:
  - `seiten[]` mit `titel`, `svg`, `kuerzel`, `hinweise`, `nicht_gezeichnet`; dazu `liste` und `ohne_lage`.
  - **Jedes SVG kommt vom Browser** und wird deshalb mit `svg_pruefung.pruefe_svg` geprüft (422 mit Name der Stufe).
  - Es geht als `data:image/svg+xml` in das HTML, bleibt also ein Bild.
  - Grenzen: höchstens 14 Seiten, je SVG höchstens 400.000 Zeichen.

## Oberfläche

**Anordnung** (`zeitachse.js`):
- `achse` stapelt die Stufen. Ein Stufenkopf mit Anmerkungen (`stufenHinweise`) wird um `hinweisHoehe(n)` höher.
- `spalten` verteilt die Breite: Achse | Leitlinien | linke Spuren | Rinne | Mitte | rechte Spuren | Leitperspektiven.
  - Die erste Spur steht rechts innen.
  - Unter `SCHMAL` zeigen die Spuren keinen Text mehr; unter `MIN_SPUR` passen sie nicht mehr.
  - Mit `fuellen` wachsen die Spuren bis `SPUR_MAX`, den Rest bekommt die Mitte.
- Weitere Bausteine: `bloecke`, `kurve` (S-Kurve), `klammer` (endet waagerecht, damit der Pfeil stimmt), `rinnenTiefen` (Intervallzuteilung), `stil`, `sichtbar`, `marken`, `randmarken`.

**Übersicht** (`VernetzungMatrix.svelte`, `vernetzung_matrix.js`):
- Reiter „Übersicht“ und „Zeitachse“; ohne Fach ist die Übersicht der Einstieg.
- Eine `<table>`, symmetrisch, damit jede Zeile vollständig ist. Text in der Zelle („A 2 · Q 3“), der Satz in `title` und `aria-label`.
- Gefüllte Zellen mit den Mengenstufen der Leitlinien-Übersicht (`--diagramm-stufe-1…5`, `heatmap_stufen.js`), mit `validate_palette.js --ordinal` auch gegen `bg` geprüft. Schrift je Stufe `--diagramm-stufe-n-tx` (nach APCA), die Warnmarke mit `--diagramm-marke-*`. Zurück zum Farbfeld neben der Zahl: `GEFUELLT = false`.
- Die Diagonale bleibt ungefärbt, sonst überstrahlt sie die Paare.
- Die Zelle ist ein Link `?fach=<Zeile>&spur=<Spalte>&stufe=`. `spur` gilt nur beim Laden und wird nicht gemerkt.

**Zustand:**
- In der Adresse: `?ansicht=uebersicht&fach=&spur=&kapitel=&schuljahr=&weg=&stufe=&entwuerfe=1`. `stufe` ist in der Zeitachse das Sprungziel, in der Übersicht die gezeigte Stufe.
- Gewählte Spuren je Fach in der Einstellung `vernetzung_spuren`.
- Hervorgehoben wird `hover ?? gewaehlt`.

**PDF-Zeichnung** (`zeitachse_svg.js`):
- Eigene Maße und immer volle Seitenbreite.
- Nur Präsentationsattribute und feste Druckfarben, kein CSS: `pruefe_svg` und weasyprint.
- Schmale Spuren tragen Kürzel („PH 3“).
- Linien über eine Stufengrenze fehlen, sie stehen in der Liste.

**Einstiege:**
- Kachel und Seitenleiste der Bibliothek, auf der Darstellungsstufe der Curricula (`seitenleiste_links.test.js`).
- Curriculum: Kopf und jedes Kapitel.
- Jahresverlaufsplan und Planer.
- Gebaut werden die Pfade mit `vernetzungPfad()`.

## Tests

- **Backend:**
  - `tests/unit/test_vernetzung_zeit.py`;
  - `tests/integration/test_vernetzung.py`: Übergangsjahr V2/V3, Weg einer Klasse, Entwürfe, Leserecht, Endpunkte, Matrix je Stufe;
  - `tests/unit/test_vernetzung_export.py` mit einem SVG aus dem Frontend als Testdatei: `tests/unit/fixtures/vernetzung_zeitachse.svg`.
- **Frontend:** `zeitachse.test.js` mit Belastungstest (16 Fächer, 576 Kapitel, rund 1.900 Bezüge), `zeitachse_svg.test.js` und `vernetzung_matrix.test.js`.

## Testwelt (Dev)

Die echten Curricula geben kaum Bezüge her. `venv/bin/python scripts/vernetzung_testwelt.py`
legt Entwürfe an:
- 19 Fächer, Kl. 7–9;
- Kapitel aus den Kompetenzen der Unterbereiche;
- Absprachen und Plan-Entwürfe.

Die Bezüge entstehen aus den echten Querverweisen des Bildungsplans. Alles trägt den Besitzer
`dev-testwelt`; `--entfernen` löscht es wieder. Das Skript bricht auf der Produktion ab.

## Bekannte Grenzen

- Bezüge zwischen zwei Spurfächern zeigt die Ansicht nicht; dafür das eine Fach in die Mitte nehmen.
- Bezüge im eigenen Fach über eine Fassungsgrenze gibt es nicht, weil die Kanten innerhalb einer Fassung liegen. Der Stufenkopf sagt es.
- Querverweise auf prozessbezogene Kompetenzen zählen nicht, weil sie für das ganze Fach gelten.
- Die Übersicht zählt Bezüge nur innerhalb einer Stufe.
