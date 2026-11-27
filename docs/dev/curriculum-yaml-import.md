# Curriculum aus YAML importieren (seit 0.56)

Päckchen BA. Eine Curriculum-YAML — Export einer anderen Plattform oder Entwurf eines
KI-Programms — wird in der Oberfläche zum **Entwurf**, nach einer Vorschau. Über MCP lässt sich
dieselbe Prüfung aufrufen, nie das Anlegen ([MCP-Server](mcp.md)).

## Schichten

| Datei | Was |
|---|---|
| `app/context/curriculum_yaml.py` | `einlesen` (Text → Prüfung), `zu_entwurf` (Daten → `CurriculumDraftConfirmed`), `verweise_pruefen` (Leserecht der Verweise), `durchlauf` (Vorschau und Anlegen), `Grenzen` |
| `app/context/service.py` | `import_curriculum_from_draft(…, als_entwurf=, kopie_von=)` — der Import selbst |
| `app/context/router.py` | `POST /context/curricula/import/pruefen`, `POST /context/curricula/import` |
| `frontend/src/lib/components/CurriculumYamlImportDialog.svelte` | Dialog; Regeln in `lib/curriculum_yaml_import.js` |
| `backend/scripts/import_curriculum.py` | Admin-Skript; nutzt `zu_entwurf(…, grenzen=None)`, sonst unverändert |
| `app/context/curriculum_stapel.py` | Sammelimport (0.62, BH): `art_bestimmen` (rein), `stapel` — je Datei `durchlauf` |
| `frontend/src/lib/components/CurriculumVorlagenDialog.svelte` | „Vorlagen einspielen“ (Admins); Regeln in `lib/curriculum_vorlagen.js` |

## Format

Das des Exports (`build_curriculum_export_dict`):

```yaml
schule: ""            # darf leer sein
fach_code: CH         # Pflicht, Kürzel aus subjects.yaml
fach: Chemie
schulart: Gymnasium   # darf leer sein
jahrgangsstufe: "8"   # Pflicht; "7/8" für ein Band
bp_version: "2016"    # Pflicht; Fassung des Bildungsplans
bp_id: BP2016BW_ALLG_GYM_CH   # findet den Fachplan in einer anderen Instanz
vorwort: …
quelle: Beispielcurriculum Chemie Gymnasium Klasse 8 (ZSL, Fassung V3.0)   # optional, ≤ 300 Zeichen (0.62)
rahmen: {wochenstunden: {"8": 2}, …}
kapitel:
  - titel: Stoffe     # Pflicht
    reihenfolge: 1    # fehlt oder doppelt → Position, mit Warnung
    std: 10
    hinweis: …
    konkretisierung: [ … ]
    lernsequenzen:
      - bp_titel: …
        reihenfolge: 1
        std: 4
        eintraege:
          - ik: [{nr: "3.2.2.1(1)", partiell: false}]
            pk: [{id: "2.1"}]
            konkretisierung: …
            hinweise: "@[BNE](lp:BNE) #[Physik](ik:PH:3.1(1)) @[Ziel 4](lba:SDG4)"
            material: "@[Arbeitsblatt](node:<uuid>)"
            begriffe: [Atom, {name: Ion, fassung: "Kl. 9"}]
            fachmethoden: [Titration]
```

Die Reihenfolge ist Teil der Schlüssel von Kapitel und Lernsequenz (`…_kapitel_<n>_ls_<m>`);
zwei gleiche Nummern legte der Import früher zu **einem** Knoten zusammen. `zu_entwurf`
nummeriert dann nach Position — aber nur dann: Ein echter Export mit eindeutigen Nummern behält
sie, damit das Skript beim Wiederimport dieselben Schlüssel trifft.

## Bereinigung

| Gefahr | Riegel |
|---|---|
| Objekt-Tags (`!!python/…`) | `SafeLoader` |
| Anker/Aliase („Billion Laughs“) — auch `safe_load` expandiert sie | `_OhneAliase` lehnt jeden Anker und Alias ab |
| tiefe Verschachtelung | Tiefe 12 (das Format braucht 6), `RecursionError` abgefangen |
| Größe | `Grenzen`: 200 KB, 30 Kapitel, 150 Lernsequenzen, 300 Einträge, 5 000 Zeichen je Feld, 50 je Liste — vor dem Parsen die Bytes. Gemessen: größtes Dev-Curriculum 20 KB, 7/24/29 |
| falsche Typen, fehlende Pflichtfelder | Fehler mit Stelle („Kapitel 3, Lernsequenz 2, Eintrag 1, pk: muss eine Liste sein.“) |
| unbekannte Felder | übergangen, Warnung |
| Steuerzeichen | entfernt, Warnung |
| Verweise unbekannter Art (`@[x](javascript:…)`) | nur der Text bleibt, Warnung |
| Verweise mit Kennung auf fremde Knoten | `verweise_pruefen`: `lp`, `lpa`, `lb`, `lba`, `ik`, `node` mit UUID nur, wenn `read_scope_clause` der Person den Knoten zeigt; sonst Text, Warnung. Der Import legte zu jeder **existierenden** Kennung eine Kante an |
| HTML im Text | unverändert (F7): Das Anzeigen bereinigt wie bei Editor-Eingaben (DOMPurify); ein Filter beschädigte Formeln wie `a < b` |
| KI-Inhalt mit Prompt-Injection | Vorschau + Entwurfsstatus: Sichtbar wird nichts ohne Veröffentlichen durch die Fachschaft |

## Entwurfsmodus des Imports

`import_curriculum_from_draft(db, payload, pseudonym, als_entwurf=True, kopie_von=None)`:

- Schlüssel `yaml_<uuid>` — trifft nie ein vorhandenes Curriculum, archiviert nichts. Ohne
  `als_entwurf` (Skript) bleibt der Schlüssel `<bp_id>_<jahrgang>`, also Aktualisieren und
  Archivieren verwaister Kapitel.
- `status = 'draft'` an Curriculum, Kapiteln, Lernsequenzen; Eigentümer:in die Person
  (`get_or_create_node` übernahm `owner_pseudonym` bis 0.56 gar nicht).
- **Keine Embeddings** für Entwürfe: Der Import rief je Kapitel sofort das Embedding-Modell —
  auch in einer Vorschau, die verworfen wird. Nach dem Veröffentlichen holt die Nachholung sie.
- `kopie_von`: ein **veröffentlichtes** Curriculum **desselben Fachs**, sonst `ValueError`. Der
  Entwurf übernimmt Titel und Band; jedes Kapitel zeigt per `kopie_von` auf das nächste freie
  gleichnamige des Originals (ohne Groß-/Kleinschreibung und Leerraum), damit die Einheiten beim
  Veröffentlichen mitwandern. „Höchstens ein offener Entwurf“ prüft der Aufrufer
  (`curriculum_entwurf.offener_entwurf`).

## Vorschau und Anlegen

`durchlauf(db, text, user, ersetzen=None, speichern=False)`:

1. `einlesen` — bei Fehlern zurück.
2. Fach per `fach_code`; `darf_entwurf_bearbeiten`, sonst `KeinRecht` (Route: 403).
3. `verweise_pruefen`.
4. Veröffentlichte Curricula gleichen Fachs, `jahrgangsstufe` und `bp_version` (`vorhanden`, je
   mit `offener_entwurf`). `ersetzen` muss darunter sein und frei.
5. `begin_nested()`, Import als Entwurf, Baum lesen, Zusammenfassung; ohne `speichern`
   Savepoint verwerfen. Die Vorschau **ist** also der Import — keine zweite Logik (F4 a).

Antwort: `ok`, `fehler`, `warnungen`, `curriculum`, `kapitel` (`titel`, `std`, `lernsequenzen`,
`eintraege`, `ersetzt_kapitel`), `summen`, `vorhanden`, `ersetzen`; nach dem Anlegen `id`.

**Routen:** `pruefen` immer 200 (Fehler im Körper), `import` 201 oder 422 mit der Vorschau als
`detail`. Beide gedrosselt im Eimer `curriculum_import` (20 / 5 min, zusammen). Kein Stand im
Verlauf beim Anlegen — den ersten hält der Editor beim ersten Speichern fest.

**Dialog:** Text oder Datei → *Prüfen*; gibt es genau ein ersetzbares Curriculum, prüft der
Dialog gleich ein zweites Mal mit `ersetzen`, damit die Vorschau zur Vorauswahl passt (F2).
Ändern sich Text oder Wahl, ist *Anlegen* gesperrt, bis neu geprüft ist.

## Sammelimport (seit 0.62)

Päckchen BH, nur Admins: `POST /context/curricula/import/stapel/pruefen` und
`POST /context/curricula/import/stapel` mit `{dateien: [{name, yaml}]}` — höchstens 60, zusammen
12 MB (`MAX_DATEIEN`, `MAX_BYTES_GESAMT`; Pydantic). Beide immer 200; Eimer `curriculum_stapel`
(10 / 10 min).

`stapel(db, dateien, user, tag=, speichern=)` je Datei:

1. `_lage`: einlesen, Fach, veröffentlichte Curricula gleicher Stufe und Fassung, Zahl der
   Entwürfe (freie Entwürfe der Stufe ∪ offene Entwürfe der veröffentlichten).
2. `art_bestimmen(vorhanden, entwuerfe, schon_im_stapel)`: `neu`; `ersetzt` bei genau einem
   veröffentlichten ohne Entwurf (dann `ersetzen=`); sonst `zusaetzlich` — auch bei mehreren
   veröffentlichten (Bänder) und wenn eine frühere Datei des Laufs dieselbe Stufe trifft. Damit
   stimmt die Vorschau mit dem Anlegen überein, obwohl die Vorschau jede Datei zurückrollt.
3. `durchlauf(…, titel_zusatz="Import TT.MM.JJJJ" bei zusaetzlich, vorlage={datei, importiert_am})`
   in einem eigenen Savepoint; unerwartete Ausnahmen werden geloggt und als Fehler der Datei
   gemeldet. Beim Anlegen Commit nach jeder Datei.

Antwort: `dateien` (die Antwort von `durchlauf` plus `datei`, `art`, `ersetzt_titel`), `zahlen`
(`ok`, `fehler`).

**Metadaten:** `metadata.quelle` kommt aus der Datei (jeder Import; Export und Kopie behalten es),
`metadata.vorlage` nur aus dem Sammelimport — `duplicate_curriculum` lässt es weg, nach dem
Veröffentlichen bleibt es stehen. Die Oberfläche zeigt `vorlageHinweis` nur an Entwürfen
(`lib/curriculum.js`). Sichtbarkeit der Import-Knöpfe: `darfCurriculaImportieren` — Admin oder
Fachschaft, wie `darf_entwurf_bearbeiten` (eine Unterrichtsgruppe genügt nicht).

**MCP:** `YAML_FORMAT` (Beschreibung von `curriculum_yaml_pruefen`) und `ANLEITUNG` nennen
`quelle` — die Vorlagen entstehen in einem KI-Programm. Wächter
`test_curriculum_stapel.py::test_mcp_kennt_quelle`.

## Tests

- `tests/unit/test_curriculum_yaml.py` — bösartige Eingaben, Meldungen mit Stelle, Grenzen.
- `tests/integration/test_curriculum_yaml_verweise.py` — Leserecht der Verweise.
- `tests/integration/test_curriculum_yaml_entwurf.py` — Entwurfsmodus, Ersatz mit Veröffentlichen.
- `tests/integration/test_curriculum_yaml_http.py` — Routen, Rechte, Drossel; die Vorschau
  hinterlässt nichts.
- `frontend/src/lib/curriculum_yaml_import.test.js` — Vorauswahl, Anlegen, Summen.
- `tests/unit/test_curriculum_stapel.py`, `tests/integration/test_curriculum_stapel_http.py` —
  Sammelimport: Art je Datei, Datum im Titel, Fehler je Datei, Rechte, Grenzen, Drossel,
  `quelle`/`vorlage` in Export und Kopie; `frontend/src/lib/curriculum_vorlagen.test.js`.
- MCP: `test_mcp_werkzeuge.py::test_curriculum_yaml_und_pruefen`, Wächter
  `test_mcp_nur_lesend.py::test_durchlauf_nur_ohne_speichern`.
