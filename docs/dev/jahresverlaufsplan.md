# Jahresverlaufsplan (seit 0.59)

Der Jahresverlaufsplan der Fachschaft legt die Kapitel oder Lernsequenzen eines Curriculums auf ein
Schuljahr: je Fach, Klassenstufe und Schuljahr eine Folge von Abschnitten mit Dauer in
Unterrichtswochen. Anwenderhilfe: `docs/user/jahresverlaufsplan.md`.

## Datenmodell

Ein Plan ist ein `ContextNode` vom Typ **`verlaufsplan`** (Kategorie `knowledge`, `school`/`subject`,
in `planung_content_types` — also nicht in Suche, Listen und Graph der Bibliothek).

- `subject_id`, `min_grade = max_grade` = Klassenstufe.
- `status`: `draft` (Entwurf) oder `active` (beschlossen). Migration 0114 erlaubt `draft` für den Typ
  und legt den eindeutigen Teilindex `uq_context_nodes_verlaufsplan` auf
  (`subject_id`, `min_grade`, `metadata->>'schuljahr'`) für `draft`/`active` — höchstens ein Plan je
  Fach, Stufe und Schuljahr.
- `read_scope = school` wie ein Curriculum (Lehrkräfte; die Seiten prüfen zusätzlich die Rolle),
  `write_scope = subject` mit der ersten Fachschaftsgruppe des Fachs als Pflichtwert. Geschrieben wird
  trotzdem nach `darf_entwurf_bearbeiten` (jede Fachschaftsgruppe des Fachs, Admins).

`metadata`:

| Feld | Bedeutung |
|---|---|
| `schuljahr` | „2026/27“ |
| `planungsart` | `sequenz` (Vorgabe für neue Pläne) oder `kapitel`; fehlt = `kapitel` |
| `abschnitte` | Liste in Planreihenfolge, je `{id, titel, wochen, kapitel_ids, sequenz_ids, notiz, puffer}` |
| `beschlossen_am` | ISO-Datum des Beschlusses |
| `uebernommen_aus` | ID des Quellplans beim Übernehmen |

Es gilt nur das Bezugsfeld der Planungsart (`BEZUGSFELD`); das andere bleibt nach einem Wechsel
stehen und wird nicht gelesen. Ein **Puffer** (`puffer: true`) hat beide Felder leer — `_metadata`
im Router erzwingt das und setzt den Titel „Puffer“, wenn keiner da ist.

**Kanten:** `bezugskanten_abgleichen` hält je genannter Sequenz bzw. jedem Kapitel eine
`references`-Kante vom Plan und keine sonst. Unbekannte IDs bekommen keine Kante.

## Eigener Schreibweg

Plan, Status und Kanten schreibt nur `app/context/verlaufsplan_router.py`
(`/context/verlaufsplaene`). Die allgemeinen Wege in `app/context/router.py` (Anlegen, PATCH,
Verwalten, Kopieren, Löschen) rufen `pruefe_eigener_weg` und antworten mit 422. Neue Typen mit
eigenem Weg kommen in `EIGENE_WEGE`.

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/context/verlaufsplaene?subject_id=` | Liste (kurz) |
| POST | `/context/verlaufsplaene` | Anlegen (Entwurf); nicht für vergangene Schuljahre (die Oberfläche bietet das laufende und das kommende an) |
| GET | `/context/verlaufsplaene/{id}` | Voll, mit `lage`, `curricula`, Rechten |
| PUT | `/context/verlaufsplaene/{id}` | Abschnitte und Planungsart speichern; `umrechnen: true` nur beim ausdrücklichen Wechsel |
| POST | `/context/verlaufsplaene/{id}/beschliessen` | Entwurf → beschlossen |
| POST | `/context/verlaufsplaene/{id}/uebernehmen` | Kopie als Entwurf in ein anderes Schuljahr |
| DELETE | `/context/verlaufsplaene/{id}` | Löschen |

Der Router steht in `main.py` **vor** `context_router`, sonst fängt dessen `/{node_id}` die Pfade ab.
Pläne vergangener Schuljahre (`ist_archiviert`) sind nur lesbar (409); Übernehmen geht auch aus dem
Archiv.

**`umrechnen`:** Ohne das Kennzeichen gelten die Abschnitte, wie sie kommen. So stellt „Rückgängig“
einen früheren Stand samt Art wieder her, ohne dass aus einzelnen Sequenzen alle Sequenzen eines
Kapitels werden. Umrechnung: `umrechnen()` (Sequenz → ihr Kapitel; Kapitel → alle seine Sequenzen).

**Übernehmen:** `bezuege_abbilden` legt die Bezüge auf das heutige Curriculum der Stufe. Was dort
steht, bleibt; sonst wird über den gleichen Titel gesucht — Sequenzen zuerst unter dem gleichnamigen
Kapitel, dann global, und nur bei genau einem Treffer. Der Rest entfällt und wird als
`kapitel_entfallen` gemeldet. Puffer und alle anderen Felder kommen unverändert mit.

## Zeitrechnung

`app/planning/verlaufsplan_zeit.py`, ohne Datenbank. Der Plan speichert nur Reihenfolge und Dauer;
`lage()` legt ihn auf den Kalender des Schuljahrs (`unterrichtswochen()` aus
`app/budget/schulwochen.py` — Ferienwochen zählen nicht, eine angebrochene Woche zählt ganz).

`Planlage` liefert je Abschnitt Woche von–bis, ersten und letzten Schultag, Ferien darin und danach,
Halbjahreswechsel, Überhang und Stunden; für den Plan `frei`, `ueberhang`, `puffer_wochen`, die
`ferienabschnitte` (für „bis zu den Ferien“) und die Bilanz je Kapitel (`_bilanz`) bzw. je Sequenz
und Kapitel (`_sequenzbilanz`). Für die Ablaufleiste außerdem `wochen` (Nr. und Montag), `ferien`
(Lücken zwischen Unterrichtswochen, ohne die nach der letzten) und `halbjahr_ab_woche`.

Puffer nennen nichts und zählen deshalb in keiner Bilanz, nur in `puffer_wochen`. 6 Wochen sind eine
Richtgröße (`lang`), keine Grenze.

## Kalender je Schuljahr

`app/planning/calendar.py`: `kalender_fuer(schuljahr)` liefert den Kalender eines Schuljahrs oder
`None`. Das laufende kommt aus `school_year.yaml`; andere liegen daneben als
`school_year_JJJJ-JJ.yaml` (`kalenderdatei`). Diese Dateien werden nach Änderungszeit
zwischengespeichert (`_kalender_aus`, lru) und wirken ohne Neustart. Ohne Kalender ist `lage`
`None` und `kalender_fehlt` gesetzt; die Oberfläche zeigt dann nur Wochen. Ablauf zum
Schuljahreswechsel: `docs/runbooks/schuljahreswechsel.md`.

## Oberfläche

| Was | Wo |
|---|---|
| Liste | `routes/(app)/knowledge/year-plans/+page.svelte` (`FaecherFilter`, `ListenZeile`, wie die Curricula) |
| Plan | `routes/(app)/knowledge/year-plans/[id]/+page.svelte`: Autosave nach 700 ms, Rückgängig über frühere gespeicherte Stände |
| Ablaufleiste | `VerlaufsplanZeitleiste.svelte`, Raster in `lib/ablaufleiste.js` |
| Editor | `VerlaufsplanEditor.svelte` |
| Bilanz | `VerlaufsplanBilanz.svelte`, Symbole `AbdeckungSymbol.svelte` |
| Helfer | `lib/verlaufsplan.js` (Texte, Farben, Dauervorschlag, Puffer, `zumSpeichern`) |

Seitenleiste und Kachel der Bibliothek nutzen den Stufen-Schlüssel **`curricula`**, keinen eigenen:
`config/ui_levels.yaml` gehört der Schule, ein neuer Schlüssel stünde dort nicht und der Eintrag
bliebe unsichtbar.

Die Ablaufleiste hat je Unterrichtswoche eine Grid-Spalte und je Ferienlücke eine schmale. Ein
Abschnitt über Ferien zerfällt in Stücke (`raster().stuecke`); die Wochenlinien in einem Block sind
ein inneres Raster mit derselben Fuge. Schraffuren: Ferien `planner-ferien-band` (wie im Planer der
Gruppe), Puffer `verlaufsplan-puffer` (gegenläufig, neutral) in `routes/layout.css`.

## Tests

- `tests/unit/test_verlaufsplan_zeit.py` — Zeitrechnung auf dem Kalender 2025/26, Ränder, Bilanz, Ablaufleiste, Puffer
- `tests/unit/test_kalender_je_schuljahr.py`, `test_verlaufsplan_umrechnen.py`, `test_verlaufsplan_kapitel_abbilden.py`
- `tests/integration/test_verlaufsplan_typ.py`, `test_verlaufsplan_endpunkte.py` — Rechte, Archiv, gesperrte allgemeine Wege, Planungsart, Übernehmen, Puffer
- `frontend/src/lib/verlaufsplan.test.js`, `ablaufleiste.test.js`

## Ausblick

Mit 0.60 (BD Teil B) soll der Planer einer Gruppe den Plan der Fachschaft als Vorlage für seine
Einheiten anbieten; Puffer werden dabei übersprungen.
