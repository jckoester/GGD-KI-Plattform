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
`_check_read_permission` und `_check_write_permission`, **vor** Eigentum und Admin-Zweig. Ein Entwurf
ohne Recht ergibt **404**, nicht 403.

`load_curriculum_tree` lädt Entwürfe mit (Kinder mit dem Status des Curriculums, `status` im Baum).
Jeder Endpunkt, der einen Baum ausliefert, prüft mit `_curriculum_lesen`.

## Rechte — eine Regel

`schreibrecht(status, subject_id, roles, fachschaften, zugeordnet)` ohne Datenbank, benutzt von
`_check_write_permission`, `_schreibrechte_setzen` (`darf_schreiben` in Listen),
`_require_curriculum_write` und `_curriculum_rechte` (Felder in `CurriculumRead`):

| | Entwurf | veröffentlicht / archiviert |
|---|---|---|
| Admin | ja | ja |
| Lehrkraft in einer Fachschaft des Fachs (`fachschafts_faecher`) | ja | ohne Zuordnung ja, mit Zuordnung nur mit Rolle `fachvorsitz` |
| alle anderen, Vorschau | nein (404) | nein |

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

- **IK des Bands:** Fach und Fassung (`metadata.bp_version`) des Curriculums, Stufen überlappend.
- **Gezählt werden die Einträge** (`eintraege[].ik` mit `partiell`, `eintraege[].pk`), nicht die
  Kanten — der Editor legt auch für Verweise in Hinweisen `references`-Kanten an.
- `anderswo`: andere **veröffentlichte** Curricula desselben Fachs und derselben Fassung, die eine
  fehlende oder partielle IK verknüpfen — ohne Stufenbedingung (Kl. 8 und 9 teilen das Band 8–10).
- `ausserhalb`: Kompetenzen des eigenen Fachs aus anderem Band oder anderer Fassung.
- `fremdes_fach`: Kompetenzen eines anderen Fachs in den Spalten IK/PK — Überbleibsel des Imports vor
  dem 25.08.2026. Reparatur: `scripts/curriculum_kompetenzen_reparieren.py`
  (`docs/admin/updates-und-wartung.md`).

Teil B (Assistent) nutzt denselben Dienst als Funktion.

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

## Bekannte Grenzen

- Tote Verweise in Hinweisen (Baustein gelöscht) speichert der Editor ohne Kante und nennt sie
  danach (`kanteAnlegen`, `toteVerweiseBeschriftungen`).
- Die Fachvorsitz-Gruppe nennt kein Fach (E10): Vorsitz gilt in jeder eigenen Fachschaft.
