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
| GET | `/context/verlaufsplaene/{id}/export?format=pdf\|docx\|odt` | Export (seit 0.60), jede Lehrkraft |

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

## Im Planer der Gruppe (0.60, Teil B)

**Welcher Plan:** `app/planning/verlaufsplan_gruppe.py`, `plan_der_gruppe` — Fach der Gruppe,
Stufe über `_group_grade` (`jahrgang_aus`: Festlegung, kleinste Klasse, Name), laufendes
Schuljahr, Entwurf oder beschlossen (Jan, FB2). Gründe ohne Plan: `kein_fach`, `keine_stufe`,
`kein_plan`. Bekommen Pläne Varianten (Todo), wählt die Gruppe hier.

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/planning/groups/{id}/verlaufsplan` | Plan (`vp.voll`) und `abschnitt_je_woche` (ISO-Woche „2026-W38“ wie `wochenSchluessel` im Planer) |
| GET | `…/verlaufsplan/vorschau` | Vorschläge je Abschnitt, schreibt nichts |
| POST | `…/verlaufsplan/anlegen` | Einheiten anlegen und Termine belegen; Antwort `{lauf_id, einheiten, stunden}` |
| POST | `…/verlaufsplan/rueckgaengig` | `{lauf_id}`: die Einheiten des Laufs löschen; 409 mit Stunden, 404 ohne Einheiten |

Router `app/planning/verlaufsplan_gruppe_router.py`, nur Lehrkräfte der Gruppe
(`require_group_teacher`).

**Vorschau** — `app/planning/verlaufsplan_vorlage.py`, `vorschau()` ist rein; den Datenbankteil
macht `vorschlaege()`. Regeln (FB3–FB5, Jan 26.11.2026, und eigene Festlegungen im Docstring):

- je Abschnitt ohne Puffer eine Einheit; Titel = Thema, sonst Kapiteltitel, sonst „Abschnitt n“;
  Kapitel = erstes (sequenzgenau: das der ersten Sequenz); Rest und Notiz in `content`;
- ersetztes Kapitel → Nachfolger über `metadata.kopie_von` (`nachfolger_der_kapitel`);
- frei = Kategorie `unterricht`, ohne Einheit, ohne Stunde, nicht angepinnt, ab heute;
- übersprungen (`grund`): `puffer`, `schon_angelegt` (gleiche `abschnitt_id`), `kapitel_vorhanden`
  (Einheit der Gruppe in diesem Schuljahr am alten oder neuen Kapitel — Einheiten aus demselben
  Plan zählen nur über ihren Abschnitt, solange es ihn gibt), `nach_schuljahresende`, `vorbei`,
  `belegt` (alle künftigen Termine belegt); ohne Termine: `ohne_termine`, Einheit trotzdem.

**Anlegen** (`anlegen`): Snapshot (Grund `edit`, Label „Vor: Einheiten aus dem
Jahresverlaufsplan“; `create_snapshot` committet selbst), dann die Gruppe `FOR UPDATE` sperren und
neu rechnen (Doppelklick); Termine mit `populate_existing` (Sitzung `expire_on_commit=False`),
belegt per bedingtem UPDATE, das nur noch freie trifft. Jede Einheit trägt
`metadata.aus_verlaufsplan` {plan_id, abschnitt_id, lauf_id, snapshot_id}, das Schuljahr des Plans
und die Farbe ihres Kapitels (`farbe_des_kapitels`, wie die Leiste).

**Rückgängig** löscht die Einheiten des Laufs; die Termine werden über
`lesson_slots.ue_node_id ON DELETE SET NULL` frei. Kein Snapshot-Restore — der nähme spätere
Änderungen mit (Abweichung von FB6). Nicht mehr, sobald eine Einheit eine Stunde hat (am Termin
oder als Entwurf `part_of`).

**Oberfläche:** `planner/VerlaufsplanSpur.svelte` (Leiste, `href` macht Blöcke zu Links,
Einstellung `verlaufsplan_spur_zu`), `PlannerTable` (Prop `wochenThemen`),
`planner/VerlaufsplanEinheitenDialog.svelte`, Leiste mit Rückgängig in der Planerseite; Texte in
`lib/verlaufsplan.js` (`wochenThemen`, `spurOhnePlan`, `GRUND_TEXT`, `vorschauSumme`, …).

## Für Programme und Export (0.60)

`vp.kompakt(voll, titel_alt=, kapitel_alt=)` ist die Fassung für Programme: Abschnitte mit
Wochen, Daten, Ferien und Bezügen als Titel mit Kennung, Bilanz, was fehlt — ohne Rechte und
Curricula-Baum. `vp.alte_titel` holt die Titel archivierter Bezüge (`nicht_mehr_im_curriculum`).
Darauf bauen die MCP-Werkzeuge `verlaufsplaene_finden` und `verlaufsplan_lesen` ([MCP](mcp.md))
und der Export: `app/context/verlaufsplan_export.py` (`aufbereiten` rein; PDF mit
`templates/verlaufsplan_pdf.html`, DOCX/ODT über den Pandoc-AST, beide quer, die Bilanz nach
`office.SEITENUMBRUCH` auf eigener Seite). Der Jahresplan-Assistent soll `kompakt` in 0.61 lesen.

## Jahresplan-Assistent (0.61)

Fähigkeit `planning` (`app/planning/assistant_tools.py`), derselbe Dienst wie der Knopf:

| Funktion | schreibt | Was |
|---|---|---|
| `get_verlaufsplan` | nein | `vp.kompakt` (mit `alte_titel`) und eine kompakte Vorschau je `nr` (`anlegen`, `grund`, `stunden`) |
| `verlaufsplan_einheiten_anlegen` | ja | `vg.anlegen(…, auslassen=[nr], titel={nr: titel})` — der Server rechnet neu; Antwort mit `lauf_id`, `angelegt`, Bilanz |
| `verlaufsplan_anlegen_zuruecknehmen` | ja | `vg.rueckgaengig(lauf_id)`, ohne `lauf_id` das jüngste Anlegen der Gruppe |

`get_plan_balance` trägt `verlaufsplan: {titel, status}` oder `null` — der Prompt liest den Plan
nur, wenn die Lehrkraft danach fragt oder die Gruppe noch keine Einheiten hat (F4, gemessen).

**`undo_last_change` geht Schritt für Schritt zurück (seit 0.61).** `restore_snapshot` legt vor
dem Wiederherstellen einen `restore`-Snapshot an; bis 0.60 nahm `undo_last_change` immer den
jüngsten Snapshot und pendelte deshalb zwischen zwei Ständen. Jetzt zählen `restore`-Snapshots
nicht, und ein zurückgenommener trägt `payload.zurueckgenommen`. Erreicht es den Snapshot „Vor:
Einheiten aus dem Jahresverlaufsplan“, solange dessen Einheiten noch da sind, stellt es ihn nicht
her, sondern verweist mit `lauf_id` auf die eigene Rücknahme — ein Snapshot löscht keine Einheiten.

**Prompt** `config/prompts/jahresplan_assistent.md` (gemessen, siehe unten). Ein ausdrücklicher
Auftrag gilt als Zustimmung (Jan, 26.11.2026). Der Seed überschreibt einen vorhandenen Assistenten
nicht — auf Prod im Editor nachziehen.

**Messung:** `backend/scripts/jahresplan_messung.py` mit `scripts/szenarien/jahresplan.yaml` —
eigene Welt je Lauf (Messfach, Curriculum, Plan, Gruppe 98061, Termine ab der nächsten
Unterrichtswoche), Messassistent aus der Promptdatei oder `--prompt-rev`, Bewertung an der
Datenbank, `--vergleich` für die Kosten je Zug, `--selbsttest`, `--trocken`. Ergebnis 0.61:
`Plaene/Messungen-Jahresplan/befund-lauf2.md`. Den Zuschlag für die Mess-Lehrkraft bucht
`app.budget.zuschlag.buche_auf` mit `erstellt_von` `dev-messung-…`.

## Tests

- `tests/unit/test_verlaufsplan_zeit.py` — Zeitrechnung auf dem Kalender 2025/26, Ränder, Bilanz, Ablaufleiste, Puffer
- `tests/unit/test_kalender_je_schuljahr.py`, `test_verlaufsplan_umrechnen.py`, `test_verlaufsplan_kapitel_abbilden.py`
- `tests/integration/test_verlaufsplan_typ.py`, `test_verlaufsplan_endpunkte.py` — Rechte, Archiv, gesperrte allgemeine Wege, Planungsart, Übernehmen, Puffer
- `tests/unit/test_verlaufsplan_gruppe.py`, `test_verlaufsplan_vorlage.py`, `test_verlaufsplan_kompakt.py`,
  `test_verlaufsplan_export.py`, `test_jahresplan_messung.py` (Kriterien der Messung);
  `tests/integration/test_verlaufsplan_gruppe.py` (Plan der Gruppe, Vorschau, Anlegen, Rückgängig,
  Wettläufe), `test_verlaufsplan_werkzeuge.py` (Funktionen des Assistenten), `test_reflow_tools.py`
  (`undo_last_change` Schritt für Schritt), `test_mcp_werkzeuge.py`
- `frontend/src/lib/verlaufsplan.test.js`, `ablaufleiste.test.js`

## Ausblick

Varianten eines Plans für Fächer, die nicht parallel unterrichten können (Todo); die Wahl steht
in `plan_der_gruppe`.
