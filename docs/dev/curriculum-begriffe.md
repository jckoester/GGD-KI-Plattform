# Begriffe und Fachmethoden im Curriculum (seit 0.44)

Einträge eines Curriculums nennen Fachbegriffe und Fachmethoden. Gespeichert werden **Namen**,
keine Kanten; ob es einen Namen als Begriff gibt, entscheidet ein Abgleich beim Lesen. Code:
`app/context/begriffe_abgleich.py`, `app/context/curriculum_begriffe.py`, Frontend
`lib/curriculum_begriffe.js`, `NamenChips.svelte`, `CurriculumTable.svelte`.

## Format

Am Eintrag in `lernsequenz.metadata.eintraege`:

```json
{"begriffe": [{"name": "Oxidation", "fassung": "Elektronen"}, {"name": "Redoxreihe"}],
 "fachmethoden": [{"name": "Säure-Base-Titration"}]}
```

- `fassung` nur, wo jemand eine gewählt hat. Fachmethoden haben dasselbe Format ohne Fassung —
  ein späterer Typ `fachmethode` kann auf dieselbe Weise andocken.
- Leere Felder stehen nicht im Eintrag. `namen_normalisieren` nimmt Texte und Objekte, zieht
  Leerraum zusammen, entfernt Dubletten (Schlüssel wie im Abgleich) und begrenzt auf 50 Namen
  je Eintrag und 200 Zeichen je Name.
- Normalisiert wird auf jedem Schreibweg: Import (`import_curriculum_from_draft`, YAML-Konverter
  `backend/scripts/import_curriculum.py`) und `PATCH /context/nodes/{id}` bei Lernsequenzen
  (`eintraege_normalisieren`). `lernsequenz` hat kein Feldschema — keine Migration nötig.

## Abgleich

`begriffe_abgleichen(db, user, subject_id, [(name, fassung)])` löst **alle** Namen in einer
Abfrage auf (Titel und passende Aliase, alle Schlüssel samt Einzahlformen) und wendet die Regeln
danach in Python an:

1. Fach und Bezugsfächer, nur Lesbares (`read_scope_clause`), nur `BEGRIFF_TYPEN`.
2. Mit Fassung zählen nur Treffer dieser Fassung.
3. Mehrere Treffer, genau einer im eigenen Fach → der.
4. Kein Treffer → Einzahlform, aber nur bei genau einem Treffer; sonst *fehlt* (nicht
   *mehrdeutig*).

`begriff_zum_titel` (Planung) läuft darauf und formuliert nur die Gründe für das Modell. Gemessen
(300 Namen): je Name 769 ms, gebündelt 12,5 ms.

⚠️ **Nicht in `load_curriculum_tree`.** Die Funktion kennt die lesende Person nicht und hat
Aufrufer (Export, Neuverknüpfen), die nur die Namen brauchen. Aufgelöst wird in
`begriffe_aufloesen(db, tree, user)`, aufgerufen von GET und PATCH `/context/curricula/{id}`.

## Auflösung neben dem Baum

`CurriculumRead.begriffe` ist eine Liste je Paar (Name, Fassung): `zustand` (*gefunden*, *fehlt*,
*mehrdeutig*), bei *gefunden* `node_id`, `titel`, `fach`, `bezugsfach`, bei *mehrdeutig*
`kandidaten`.

⚠️ **Nicht in die Einträge schreiben.** Der Editor schickt die Einträge als Ganzes zurück; eine
Auflösung darin landete in der Datenbank. Für frisch getippte Namen gibt es
`POST /context/curricula/{id}/begriffe/aufloesen` — jede Schreibweise einzeln, damit der Editor
die Antwort seinen Chips zuordnen kann.

## Endpunkte

| Endpunkt | Zweck |
|---|---|
| `POST /context/curricula/{id}/begriffe/aufloesen` | Namen nachreichen (lesend; POST wegen der Fassung im Körper) |
| `GET /context/curricula/{id}/fachmethoden?q=` | Fachmethoden der lesbaren Curricula des Fachs mit Anzahl |
| `GET /context/curricula/{id}/begriffe/fehlend?format=json\|txt\|zip` | Übersicht, Liste, Gerüste |

Alle prüfen das Leserecht am Curriculum. Der Wächter `tests/unit/test_curriculum_routes.py` kennt
sie.

## Gerüste

Das Zip enthält je fehlendem Begriff eine Datei im Vault-Format mit `geruest: true` und leerer
`## Definition`, dazu `_Hinweise.txt` (Unterstrich: der Import übergeht sie). Der
Fachbegriffe-Import weist ein Gerüst **ohne** Definition ab (`uebergangen`); mit Definition ist es
eine gewöhnliche Datei. Dateien ohne Kennzeichnung und ohne Definition bleiben Stubs (A8).

## Umbenennen

Der alte Titel eines Begriffs bleibt Alias (`aliase.mit_altem_titel`) — in `update_node` (nach der
Kollisionsprüfung), `verwalte_node` und `update_node_title`. Im Import stehen frühere Titel als
`metadata.alte_titel` am Knoten und gehen bei jedem Lauf in Aliase und `seed_hash` ein; sonst hielte
der nächste Lauf den Alias für eine Handänderung oder entfernte ihn.

⚠️ `update_node` weist das Leeren von `subject_id` bei Fachbegriffen ab (422): Ein Begriff ohne
Fach findet weder Curriculum noch Planung. Der Baustein-Editor schickte bis 0.44 `null`, wenn
keine eigene Fachschaft gewählt war.

## Planung

- `_kapitel` (→ `zusammenhang.kapitel`, `get_unit_detail`) trägt je Lernsequenz
  `begriffe_im_curriculum` (Form von `refs`) und `begriffe_im_curriculum_ohne_baustein` —
  nur, wenn belegt.
- Der Begriffsvorschlag bekommt die Begriffe des Kapitels als eigene Zeile
  ([Begriffsvorschlag](begriffsvorschlag.md)).
- Der Prompt des Stundenassistenten (`config/prompts/stundenentwurf_assistent.md`) sagt, wie er
  sie nutzt. Messung: `scripts/szenarien/curriculum_begriffe.yaml` (Aufbau über
  `curriculum_vorher`, Kriterium `vorschlag.nicht`).

## Export

PDF und DOCX/ODT: Zeilen „Begriffe: …" und „Fachmethoden: …" unter der Konkretisierung
(`namen_fuer_export`). YAML: Text, mit Fassung als Objekt (`namen_fuer_yaml`).
