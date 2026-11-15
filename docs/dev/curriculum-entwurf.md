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

## Bekannte Grenzen

- Tote Verweise in Hinweisen (Baustein gelöscht) speichert der Editor ohne Kante und nennt sie
  danach (`kanteAnlegen`, `toteVerweiseBeschriftungen`).
- Die Fachvorsitz-Gruppe nennt kein Fach (E10): Vorsitz gilt in jeder eigenen Fachschaft.
