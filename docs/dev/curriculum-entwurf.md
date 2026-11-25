# Entwürfe, Veröffentlichen und Abdeckung von Curricula (seit 0.45)

Ein Curriculum-Baum (`curriculum` → `kapitel` → `lernsequenz`) kann ein **Entwurf** sein
(`status = 'draft'`). Code: `app/context/curriculum_entwurf.py` (Regeln),
`app/context/curriculum_veroeffentlichen.py`, `app/context/curriculum_abdeckung.py`,
`app/context/kompetenz_reparatur.py`; Frontend `CurriculumFreigabe.svelte`,
`CurriculumAbdeckung.svelte`, `lib/curriculum_freigabe.js`, `lib/curriculum_abdeckung.js`.
Entscheidungen: Plan „Curriculum-Assistent, Teil A“, ADR-019 Nachtrag K2.

## Status `draft`

- Check-Constraint `check_context_nodes_status` um `draft` erweitert, dazu
  `check_context_nodes_draft_typ`: `draft` nur an den drei Curriculum-Typen (Alembic 0106).
  Rücknahme macht Entwürfe zu archivierten Knoten.
- **Entsteht:** `POST /context/curricula/new` (immer), `duplicate_curriculum` (Kopie: ganzer Baum,
  `owner` = kopierende Person, `metadata.kopie_von` an Curriculum und Kapiteln, Vektor des
  Originals). `POST /context/nodes` nimmt `status: "draft"` für Kapitel und Lernsequenzen; zusätzlich
  macht `erbe_entwurf` in `POST /context/edges` einen **frischen** Teil (ohne jede Kante), der per
  `part_of` in einen Entwurf gehängt wird, selbst zum Entwurf.
- **Verlässt ihn nur über** `POST /context/curricula/{id}/publish`. `pruefe_statuswechsel` weist auf
  dem generischen PATCH und auf `PATCH …/verwalten` jeden Wechsel von und nach `draft` ab.
- `pruefe_kante`: Auf einen Entwurf zeigt nur ein Entwurf (sonst hinge etwa eine Einheit an einem
  unsichtbaren Kapitel). `copy_node` lehnt Entwurfsteile ab.

⚠️ **Die Lesewege filtern nicht alle auf `active`.** Suche, Retrieval, Embedding-Nachholung,
Curriculum-Resolver, „Meine Bausteine“ und `list_curricula_by_subject` tun es — die direkten Wege
(`GET /context/nodes/{id}`, Umgebung, Kanten, Kopieren) nicht. Deshalb greift die Regel in
`_check_read_permission` und `_check_write_permission`, **vor** Eigentum und Admin-Zweig. Wer den
Entwurf nicht lesen darf, bekommt **404**; wer ihn liest, aber nicht bearbeiten darf, **403**
(„Entwürfe bearbeitet die Fachschaft des Fachs.“, seit 0.52).

`load_curriculum_tree` lädt Entwürfe mit (Kinder mit dem Status des Curriculums, `status` im Baum).
Jeder Endpunkt, der einen Baum ausliefert, prüft mit `_curriculum_lesen`.

## Lesen und Bearbeiten — zwei Regeln (seit 0.52)

Bis 0.52 regelte `darf_entwurf` Lesen und Bearbeiten zugleich (E7: nur die Fachschaft). Seit
Päckchen AZ sind es zwei:

| | Regel | Prüfung (Fehler) | Wer |
|---|---|---|---|
| Lesen | `darf_entwurf_lesen(user)` — synchron, nur Rollen | `pruefe_entwurf_lesen` (404) | Lehrkraft oder Admin; nicht Schüler:innen, nicht die Vorschau |
| Bearbeiten | `darf_entwurf_bearbeiten(db, subject_id, user)` | `pruefe_entwurf_bearbeiten` (404, sonst 403) | Admin oder Lehrkraft in einer Fachschaft des Fachs |

- **Lesen** nutzen nur `_check_read_permission`, `_curriculum_lesen` und `_lesbare_curricula`.
- **Bearbeiten** nutzen alle schreibenden Wege: `_check_write_permission`,
  `_require_curriculum_write`, `create_node` (Teile als Entwurf), Kanten **in** einen Entwurf
  (`create_edge` — sonst hängte eine andere Fachschaft ein eigenes Kapitel hinein, `erbe_entwurf`),
  „Als Entwurf kopieren“, Löschen, `_curriculum_rechte` (`darf_kopieren`) und der
  Curriculum-Assistent (`zugang`).
- Suche, Retrieval, Embeddings und Planung bleiben ohne Entwürfe — sie filtern auf `active`,
  unabhängig vom Leserecht.

**Wächter:** `tests/unit/test_entwurf_leserecht_waechter.py` verfolgt per AST über `app/`, wer die
Leseregel direkt oder über Hilfsfunktionen erreicht. Jede Stelle ist eine reine GET-Route, eine
bekannte lesende Hilfsfunktion (`LESEND`) oder steht in `ERLAUBT` — mit Grund und der Prüfung, die
sie danach aufrufen muss (der Test prüft, dass sie es tut). Wer eine neue Route baut, die einen
Entwurf über `_check_read_permission` holt und dann ändert, bekommt hier den Fehler, nicht in
Produktion.

## Rechte am Curriculum — eine Regel

`schreibrecht(status, subject_id, roles, fachschaften, zugeordnet)` ohne Datenbank, benutzt von
`_check_write_permission`, `_schreibrechte_setzen` (`darf_schreiben` in Listen),
`_require_curriculum_write` und `_curriculum_rechte` (Felder in `CurriculumRead`):

| | Entwurf | veröffentlicht / archiviert |
|---|---|---|
| Admin | ja | ja |
| Lehrkraft in einer Fachschaft des Fachs (`fachschafts_faecher`) | ja | ohne Zuordnung ja, mit Zuordnung nur mit Rolle `fachvorsitz` |
| alle anderen, Vorschau | nein (Lehrkräfte 403, sonst 404) | nein |

- `fachvorsitz_zugeordnet()`: ob `group_role_map` in `auth.yaml` eine Gruppe auf `fachvorsitz` abbildet —
  je Prüfung frisch gelesen. Die Integrationstests stellen es per autouse-Fixture ab
  (`tests/integration/conftest.py`), Tests mit Fachvorsitz schalten es ein.
- Veröffentlichen = Recht am veröffentlichten Curriculum. Reaktivieren, Archivieren und Löschen
  veröffentlichter Curricula gehen über `_check_write_permission` und damit über dieselbe Regel.
- `darf_loeschen` (Curriculum als Ganzes): Entwurf → wer ihn angelegt hat, sonst wie Veröffentlichen.
- ⚠️ Die Testanmeldung (`yaml_test`) wendet die `group_role_map` nicht an — auf Dev bekommt eine
  Testperson die Rolle über `roles:` in `test_users.yaml`.

## Veröffentlichen und Ersetzen

`GET …/publish` liefert die Übersicht (Stunden, IK-Abdeckung, fremdes Fach, veraltet, Begriffe,
Vorgänger, Einheiten), `POST …/publish` veröffentlicht:

1. Baum `draft` → `active`.
2. Ist `metadata.kopie_von` ein **aktives** Curriculum: Einheiten des **laufenden Schuljahrs**
   (`metadata.schuljahr`) mit `references`-Kante auf ein Kapitel des Vorgängers wandern auf das Kapitel
   der Kopie mit passendem `kopie_von`. Ohne Entsprechung bleibt die Kante. Danach wird der Baum des
   Vorgängers `archived`.
3. Audit `admin.curriculum_published` (Fach, Vorgänger, Zahl der umgehängten / verbliebenen Einheiten).

Die Übersicht nennt bei Einheiten ohne neues Kapitel nur Gruppe und Kapitel, keine Titel — das sind
Planungsdaten anderer Lehrkräfte.

`POST …/copy` („Als Entwurf kopieren“): Fachschaft, Titel bleibt, höchstens ein offener Entwurf je
Curriculum (409 mit `entwurf_id`).

**Planung:** `UnitRead.kapitel_archiviert`, `ArchivEinheit.kapitel_ersetzt`,
`LessonUeContext.kapitel_ersetzt` speisen das Banner (`ersetztHinweis`). `pruefe_kapitel`
(`app/planning/service.py`) lässt neue Verknüpfungen nur mit aktiven Kapiteln zu; ein schon
verknüpftes archiviertes Kapitel bleibt beim Ändern von Titel oder Farbe erhalten. Der
Stundenassistent liest archivierte Kapitel nicht und fällt auf die passenden Curricula zurück.

## Abdeckung

`GET /context/curricula/{id}/coverage` (`abdeckung(db, tree)`):

- **IK des Bands** (seit 0.46, `band_des_curriculums`): die IK unter der Bandüberschrift des
  Bildungsplans, die dem Curriculum zugeordnet ist (siehe [Bänder](#bänder-des-bildungsplans-seit-046)).
  Ohne Zuordnung (parallele Bänder ohne Wahl) die IK aller Bänder, die die Stufen berühren; die
  Antwort nennt dann `baender_zur_wahl` und einen `hinweis`. Bis 0.45 zählten nur die Stufen —
  ein Oberstufen-Curriculum maß gegen Basis- und Leistungsfach zusammen, und IK ohne Stufen
  (Physik V2, Basisfach 11/12) zählten in jedem Band.
- **Gezählt werden die Einträge** (`eintraege[].ik` mit `partiell`, `eintraege[].pk`), nicht die
  Kanten — der Editor legt auch für Verweise in Hinweisen `references`-Kanten an.
- `anderswo`: andere **veröffentlichte** Curricula desselben Fachs und derselben Fassung, die eine
  fehlende oder partielle IK verknüpfen — ohne Stufenbedingung (Kl. 8 und 9 teilen das Band 8–10).
- `ausserhalb`: Kompetenzen des eigenen Fachs aus anderem Band oder anderer Fassung.
- `fremdes_fach`: Kompetenzen eines anderen Fachs in den Spalten IK/PK — Überbleibsel des Imports vor
  dem 25.08.2026. Reparatur: `scripts/curriculum_kompetenzen_reparieren.py`
  (`docs/admin/updates-und-wartung.md`).

Teil B (Assistent) nutzt denselben Dienst als Funktion.

## Bänder des Bildungsplans (seit 0.46)

`app/context/bp_baender.py`. Ein **Band** ist eine Bandüberschrift im `breadcrumb` der IK
(„3.1 Klassen 5/6“, „3.4 Klassen 12/13 (Leistungsfach)“); Schlüssel ist die Überschrift ohne
Nummer, weil die Nummer zwischen Fassungen wechselt. Geprüft am 17.11.2026: Alle 10 098 geltenden
und kommenden IK tragen eine. Stufen aus `min_grade`/`max_grade` der IK, sonst aus der
Überschrift (Physik V2 führt die Basisfach-Bänder 11/12 ohne Stufen). IK ohne Bandüberschrift
(nur in Testdaten) gehen nach Stufen.

- **Parallele Bänder:** In 27 Fach-Fassungen gibt es zu denselben Stufen zwei oder drei Bänder
  (Basis-/Leistungsfach, Physik zwei Basisfach-Schwerpunkte). `band_zuordnen` nimmt
  `metadata.band`, wenn es unter den Kandidaten ist, sonst den einzigen Kandidaten, sonst keinen.
- **Setzen:** Editor über `PATCH /context/nodes/{id}` (geprüft: nur ein Kandidat der Stufen,
  sonst 422), Auswahl aus `GET /context/curricula/{id}/band` (`CurriculumBandWahl.svelte`);
  `lege_curriculum_an` fragt bei parallelen Bändern nach (`band`). `band` steht nicht im
  `import_key` (der wird beim Ändern der Stufe segmentweise umgeschrieben); die Idempotenz von
  `curriculum_anlegen` vergleicht es mit.
- **Übersicht:** `GET /context/curricula/by-subject/{id}/overview` (`curriculum_baender.uebersicht`)
  — Fassungen (geltend, kommend, älter mit Curricula), je Fassung die Bänder mit ihren Curricula,
  dazu `nicht_zugeordnet`. Gleiche Leseregel wie die Liste (`_lesbare_curricula`). Frontend
  `CurriculumList.svelte`, Hilfen `lib/curriculum_baender.js`.
- **Abdeckung über das Band:** `GET …/by-subject/{id}/band-coverage?bp_version&band&entwuerfe`
  — IK des Bands über alle zugeordneten Curricula (verknüpft, sobald eines voll; partiell, wenn
  nur teilweise). **Abdeckung über die Fassung:** `GET …/pk-coverage?bp_version&entwuerfe` — PK
  über alle Curricula des Fachs in der Fassung, auch ohne Band. In beiden ersetzt mit
  `entwuerfe` ein Entwurf mit `kopie_von` das Original (`_ohne_ersetzte`). `format=pdf`
  (`nur_luecken`) rendert `templates/abdeckung_pdf.html` mit weasyprint. Seite
  `/knowledge/curricula/coverage?fach&fassung[&band][&entwuerfe=1]`.

## Kommende Fassung (`upcoming`, seit 0.46)

Eine Bildungsplan-Fassung, die laut Fahrplan erst später gilt, legt der Import als
`status = 'upcoming'` ab statt als `archived` (`_archive_subject_edition` in
`scripts/import_bildungsplan.py`, `kommt_ab` in `app/context/editions.py`, Alembic 0107 mit
`check_context_nodes_upcoming_typ`: nur Bildungsplan-Typen). Gilt sie, setzt der nächste Import
sie wieder `active` — auch der eines anderen Fachs. Der Löschlauf fasst nur `archived` an.

- **Unsichtbar** für alles, was `active` liest: Suche, Retrieval, Chat, Embedding-Nachholung,
  `GET /context/subjects/{id}/active-bp-version`.
- **Lesbar** über `BP_STATUS_CURRICULUM` (`editions.py`) für die Curriculum-Wege:
  `GET /context/nodes` **mit `bp_version`** (Auswahllisten für IK und PK) oder mit
  `status=active&status=upcoming` (Fachplan-Auswahl beim Anlegen), `POST /curricula/new`,
  `GET /fachplan/by-subject` (nur ausdrücklich gewählt; `kuenftige_versionen`), Kanten auf
  das Ziel, Abdeckung, Export, `resolve_ik_node`/`resolve_pk_node`/`resolve_fachplan`
  (ohne Fassung gewinnt die geltende).
- `ContextNodeRead.gilt_ab` (Startjahr) an `upcoming`-Knoten, ohne eigene Stufen nach den
  Stufen des Fachs; `archived-references` meldet `upcoming`-Ziele mit „gilt ab“.
- Die Abdeckung zählt nur `active`/`upcoming` der Fassung; archivierte Doppel derselben Fassung
  (alte `bp_id`-Schreibweise) fallen heraus. Hat die Fassung nur archivierte Knoten (abgelöste
  Fassung), zählen die.
- „Bildungsplan aktualisieren“ (`relink.py`) zielt weiter auf die geltende Fassung.

## Rückgängig (seit 0.46)

`app/context/curriculum_verlauf.py`, Tabelle `curriculum_snapshots` (Alembic 0108, CASCADE mit dem
Curriculum, höchstens `VERLAUF_LIMIT` = 30 je Curriculum). Routen: `GET`/`POST
/curricula/{id}/history` (Verlauf lesen; Stand sichern — der Editor ruft das vor dem Speichern und
speichert nicht, wenn es scheitert), `POST /curricula/{id}/undo`. Rechte: `_require_curriculum_write`.

- `sichern(db, id, grund=, von=)`: Knoten (Felder aus `FELDER`, ohne Status und Vektor) und alle
  Kanten, die einen Baumknoten berühren. `grund` `editor` oder `assistant` (Teil B, vor jedem Stapel).
  `created_at` aus Python, damit zwei Stände in einer Transaktion eine Reihenfolge haben.
- `zuruecknehmen(db, curriculum)`: jüngsten Stand anwenden und löschen — neue Teile löschen,
  gesicherte mit derselben Kennung zurückschreiben bzw. neu anlegen (der Editor löscht hart),
  Kanten **aus** dem Baum ersetzen, Kanten **in** den Baum nur ergänzen (eine Einheit, die seitdem
  an ein Kapitel gehängt wurde, bleibt). **Der Status bleibt der heutige.** Geänderte Knoten
  verlieren den Vektor (Nachholung nur für `active`).
- Kein Wiederholen (Redo).

## Rahmenangaben (seit 0.46)

`app/context/curriculum_rahmen.py`, Spiegel im Frontend `lib/curriculum_rahmen.js`, Anzeige
`CurriculumRahmen.svelte` (Editor und Leseansicht). Keine Migration: Die Angaben stehen als
`metadata.rahmen` am Curriculum-Knoten.

```json
{"wochenstunden": {"7": 2, "8": 1.5},
 "lehrwerk": "…", "beschluesse": "…", "schwerpunkte": "…", "absprachen": "…"}
```

- `rahmen_normalisieren` prüft und bereinigt (Wochenstunden 0–10 in halben Stunden, Schlüssel =
  Klassenstufe, Textfelder getrimmt, leere fallen weg, unbekannte Schlüssel auch). Aufgerufen in
  `PATCH /context/nodes/{id}` für `curriculum` (422 bei unbrauchbaren Werten) und im Zwischenformat
  `CurriculumDraftConfirmed.rahmen` (Import, YAML-Konverter).
- `verplanbar(rahmen, jahrgangsstufe)`: 30 × Wochenstunden über alle Stufen des Bands (E19);
  `None`, solange eine Stufe fehlt. Grundlage für `get_hour_frame` des Assistenten.
- Export: YAML-Feld `rahmen` (nur wenn belegt), PDF und DOCX/ODT mit Abschnitt „Rahmen“ vor dem
  ersten Kapitel (`rahmen_abschnitte`; Textfelder als Markdown).
- ⚠️ Der Import ersetzt die Metadaten des Curriculums: Ein YAML ohne `rahmen` über ein
  vorhandenes Curriculum importiert, löscht dessen Rahmen.
- Kopieren als Entwurf, Veröffentlichen und Rückgängig nehmen den Rahmen mit (Teil der Metadaten).

## Funktionen des Curriculum-Assistenten (seit 0.46)

**Nur für Lehrkräfte, nur von Admins vergeben.** Den Assistenten braucht die Fachschaft; geseedet
als „Curriculum-Entwurf“ (`config/assistants.example.yaml`, Prompt
`config/prompts/curriculum_assistent.md`). `app/api/assistants.py`: `NUR_ADMIN_FAEHIGKEITEN` /
`NUR_ADMIN_PRODUKTE` übergeht die Fähigkeit und die Marke bei Nicht-Admins (Anlegen, Ändern, Import —
eine vorhandene bleibt stehen), `_pruefe_nur_lehrkraefte` weist sie bei Zielgruppe `student`/`all` ab
(422, auch für Admins). Der Editor zeigt das Häkchen nur Admins.

Fähigkeit `curriculum_planning` (`FAEHIGKEITEN`, im Assistenten-Editor „Curriculum-Entwurf“).
Registrierung `app/context/curriculum_tools.py`, Arbeit `app/context/curriculum_assistent.py`.
`tools_for` schaltet sie frei, wenn der Assistent sie führt und die Person die Rolle `teacher` hat —
ohne Gruppenbezug, wie die Stundenplanung. Marke „erstellt Curricula“ (`produces: curriculum`).

| Funktion | liest/schreibt | Inhalt |
|---|---|---|
| `get_curriculum_draft` | liest | Baum mit Rahmen, Kennungen, Einträgen; Kompetenzen als Nummern (`ik`, `ik_teilweise`, `pk`), Begriffe mit `zustand` |
| `get_bp_competences` | liest | ohne `bereich` Übersicht (Bereich = `thematische_gruppe`, Anzahl, Nummernspanne); mit `bereich` (Name, Teil davon, Nummernpräfix, `alle`) die Texte; `typ: pk` |
| `get_curriculum_coverage` | liest | Abdeckung (Teil A) als Zahlen und Nummern, ohne Texte |
| `get_hour_frame` | liest | `verplanbar` (30 × Wochenstunden), `verplant` (Summe der Lernsequenzen), `rest`, `fehlende_stufen` — für den gespeicherten Stand |
| `preview_curriculum_operations` | liest | Prüflauf: derselbe Stapel wie beim Schreiben, ohne Sichern und Schreiben; Antwort wie unten, `geschrieben: false`, neue Teile mit `id: null` |
| `apply_curriculum_operations` | schreibt | Stapel aus `kapitel_*`, `lernsequenz_*`, `eintrag_*` (anlegen, ändern, löschen; `position` ab 1; `ref` für eben Angelegtes). Antwort: `gliederung`, `verplant`, `verplanbar`, `rest` (null ohne Wochenstunden, dann `fehlende_stufen`), `geloescht` (nur wenn etwas wegfällt), `neue_kennungen` |
| `set_curriculum_frame` | schreibt | Rahmenangaben ergänzen (Wochenstunden je Stufe zusammengeführt); die Antwort auf eine Rahmenfrage gilt als Zustimmung |
| `undo_last_curriculum_change` | schreibt | `zuruecknehmen` aus dem Verlauf — derselbe wie im Editor; fremde Stände nur mit `auch_fremde` (siehe unten) |
| `finde_curriculum` | liest | Curricula der eigenen Fachschaften (Admin: alle), gefiltert nach Fach und Band, mit `offener_entwurf_id`; je Fach die Fassungen zum Anlegen |
| `waehle_curriculum` | Bezug | setzt das Bezugscurriculum; veröffentlicht mit offenem Entwurf → der Entwurf; ohne → nur lesen, mit `als_entwurf_kopieren` eine Kopie |
| `lege_curriculum_an` | schreibt | leerer Entwurf am Fachplan (`curriculum_anlegen`, dieselbe Funktion wie `POST /curricula/new`); nicht, wenn es für Band und Fassung schon eins gibt |

- **Zugang:** `zugang()` ruft `_require_curriculum_write` (die Regel des Editors) — auch zum Lesen.
  Schreiben zusätzlich nur bei `status == draft` (E17), sonst `NUR_ENTWUERFE`. Bezug:
  `curriculum_id` im Aufruf oder `ToolContext.curriculum_node_id` (Vorgabe, keine Erlaubnis).
- **Kompetenzen des Bands:** `kompetenzen_des_bands()` in `curriculum_abdeckung.py` — dieselbe Menge
  für Abdeckung, `get_bp_competences` und die Prüfung der Nummern. Eine Nummer außerhalb (anderes
  Band, andere Fassung, erfunden) weist der Stapel ab.
- **Ganz oder gar nicht:** `_planen()` wendet alle Operationen erst im Speicher an (`_Plan`); bei
  einem Fehler wird nichts geschrieben und kein Stand gesichert. Der Prüflauf
  (`operationen_pruefen`) endet hier; Prüflauf und Schreiben antworten über dasselbe `_ergebnis()`,
  also mit derselben Gliederung, Stundenbilanz (`_bilanz`, wie `get_hour_frame`) und `geloescht`
  (Kapitel, Lernsequenzen, Einträge gegenüber dem Stand vorher — Inhalt gelöschter Kapitel
  mitgezählt, Verschobenes nicht). Der Prüflauf ist eine eigene Funktion, kein Schalter am
  Schreiben: Ein vergessener Schalter schriebe ohne Zustimmung. Beim Schreiben
  `sichern(grund="assistant")`, dann
  schreiben: Gelöschtes zuerst (CASCADE), neue Teile als Entwurf der aufrufenden Person,
  `reihenfolge` neu durchgezählt, Kapitel-`std` = Summe der Lernsequenzen, Kanten der geänderten
  Lernsequenzen wie im Editor (`_soll_kanten` ≙ `deriveRefsFromEntries`: IK `references` mit
  `partiell`, PK `develops`, Verweise in Hinweisen `references`, Material `used_with`).
- **Geprüfter Vorschlag:** Ein bestandener Prüflauf wird an der Unterhaltung gemerkt
  (`conversations.curriculum_vorschlag`, Migration 0110: Curriculum, Operationen, `stand_kennung`).
  Nach der Zustimmung schreibt `apply_curriculum_operations` **ohne** `operations` genau diesen
  Stapel — die Funktionsantworten der vorigen Nachricht kennt das Modell nicht mehr. Hat sich das
  Curriculum seitdem geändert (Prüfsumme über dieselben Felder wie ein gesicherter Stand), wird
  nichts geschrieben. Nach dem Schreiben ist der Vorschlag verbraucht.
- **Veröffentlichte Curricula:** `zugang()` lässt die ganze Fachschaft lesen, als Bezug wählen
  und als Entwurf kopieren (`darf_entwurf_bearbeiten`, wie „Als Entwurf kopieren“ im Editor), auch wenn ein
  Fachvorsitz zugeordnet ist und das Schreibrecht des Editors nur ihn hat.
- **Rückgängig:** Ohne Rückfrage nimmt `undo_last_curriculum_change` nur einen Stand zurück, den
  der Assistent für dieselbe Person gesichert hat (`reason == "assistant"` und
  `created_by == user.sub`). Sonst schreibt er nichts und antwortet mit `bestaetigung_noetig` und
  `letzte_aenderung {von, von_mir, zeit, gegenstand}` (ohne Pseudonym); erst `auch_fremde: true`
  nimmt zurück. `gegenstand` (`curriculum_verlauf.gegenstand()`) vergleicht den Stand mit dem
  heutigen Baum: `rahmen` (Rahmenangaben), `inhalte` (alles andere). Der Grund des Stands bleibt
  `editor`/`assistant` (Prüfbedingung `check_cs_reason`); `set_curriculum_frame` sichert also mit
  `assistant` wie ein Stapel. Der Editor-Weg (`POST /curricula/{id}/undo`) fragt nicht.
- Kein Commit in den Funktionen; der Chat committet am Ende der Antwort.
- **Messung:** `backend/scripts/curriculum_assistent_messung.py` mit
  `scripts/szenarien/curriculum_assistent.yaml` (je Lauf ein Mess-Curriculum aus einer Vorlage,
  danach gelöscht; `--selbsttest` ohne Schreiben, `--trocken` ohne Modellaufrufe). Argumente und
  Ergebnisse der Funktionen liest sie aus dem Messkanal `vorab_debug` (Feld `curriculum`, nur
  außerhalb der Produktion). Stand 16.11.2026, je 10 Fälle × 3 Läufe: `chat-komplex` 22/30
  (1,39 $), `chat-standard` 7/30 (löscht ohne Zustimmung, bleibt stehen), `mistral-large` 26/30
  (0,48 $). Seed: `chat-komplex`. Die Umbenennung der Vorschau (vorher
  `check_curriculum_operations`) änderte an `chat-komplex` nichts messbar.
- **Bereich einer Kompetenz** (`bereich_von` in `curriculum_abdeckung.py`): `thematische_gruppe`,
  sonst die letzte Überschrift im `breadcrumb` („3.1.7 Optik“) — `thematische_gruppe` ist in den
  meisten Fächern leer. Gilt für die Abdeckung und `get_bp_competences`.
- **Funktionsantworten bleiben nicht im Verlauf.** Gespeichert wird nur der Antworttext
  (`messages.content`, dazu `werkzeuge_mit_wirkung`); Kennungen aus einem früheren Lesen kennt
  das Modell in der nächsten Nachricht nicht mehr. Wer nach einer Zustimmung schreibt, liest
  deshalb in derselben Antwort neu (Prompt: „frisch lesen“).

### Bezug der Unterhaltung

`conversations.curriculum_node_id` (Alembic 0109, SET NULL), Dienst `app/context/curriculum_bezug.py`.

- **Setzen** beim Anlegen (`ChatRequest.curriculum_node_id`, aus dem Knopf „Assistent“ in Editor und
  Ansicht eines Entwurfs, `?curriculum_id=` → `chatVorgaben`) oder im Gespräch (`waehle_curriculum`,
  `lege_curriculum_an` → `bezug_setzen`; gilt sofort, der Router übernimmt `ctx.curriculum_node_id`).
  Nicht zusammen mit einem Stundenbezug (422 beim Anlegen; `bezug_setzen` löscht ihn). Die
  Unterhaltung bekommt das Fach des Curriculums, keine Gruppe.
- **Lesen** bei jedem Prompt-Aufbau neu mit `zugang` (Regel des Editors): Systemzeile `bezugszeile`,
  Anzeige `bezug_fuer_anzeige` im Ereignis `bezug` und in `GET /conversations/{id}` (`curriculum`);
  der Chatkopf verlinkt einen Entwurf in den Editor, ein veröffentlichtes in die Ansicht.
- Ohne passenden Assistenten öffnet der Knopf den Chat trotzdem; die Chatseite nennt die fehlende
  Fähigkeit (`einstiegsFaehigkeit` → `curriculum_planning`).

## Querverweise in andere Fächer (seit 0.58)

Der Bildungsplan nennt an Kompetenzen, wo ein anderes Fach anschließt; der Import legt das als
Kanten `related_to` an (`scripts/import_bildungsplan.py`, Kasten `box--f`). Gelesen wird es in
`app/context/querverweise.py`, ausgeliefert über **einen** Weg, `POST /context/querverweise`
mit `{kompetenz_ids, nur_veroeffentlicht}` (POST wegen der Listenlänge, in `vorschau.ERLAUBT`).

- **Nur Bildungsplan-Knoten** (`ik_kompetenz`, `leitidee`, `pk_kompetenz`) als Quelle und Ziel;
  andere IDs werden übergangen. Deshalb keine Prüfung am Curriculum — derselbe Weg dient
  Lesesicht, Editor (auch ungespeicherte Kompetenzen) und Bildungsplan-Ansicht.
- **Beide Richtungen**, ein Fach nie auf sich selbst. **Bereiche** (`leitidee`) bleiben
  Bereiche: Gut die Hälfte der Verweise im Plan zielt auf einen Bereich.
- **Archivierte Ziele** werden über (Fach, Typ, Nummer, Stufenband aus `bp_id`) auf die aktive,
  sonst künftige Fassung umgelenkt; ohne Treffer fallen sie weg. Das Band gehört in den
  Schlüssel, weil Nummern sich zwischen Bändern wiederholen. Künftige Ziele tragen
  `ab_schuljahr` (`gilt_ab_schuljahr`).
- **Fundstellen** (mit Person): `leitlinien_fundstellen` auf die Ziele, gefiltert auf
  Curricula **des Zielfachs**; ein Bereich zählt über seine Kompetenzen (`part_of`, auch über
  Unterbereiche). Entwürfe wie in der Leitlinien-Übersicht.
- Anzeige: `lib/components/Querverweise.svelte`, Logik `lib/querverweise.js`. Export:
  `faecher_je_kompetenz` → „↔ PH, CH“ in PDF (`.ik-qv`) und DOCX/ODT. MCP: siehe
  [MCP](mcp.md).

## Bekannte Grenzen

- Tote Verweise in Hinweisen (Baustein gelöscht) speichert der Editor ohne Kante und nennt sie
  danach (`kanteAnlegen`, `toteVerweiseBeschriftungen`).
- Die Fachvorsitz-Gruppe nennt kein Fach (E10): Vorsitz gilt in jeder eigenen Fachschaft.
