# Leitlinien der Schule

Seit 0.50 (Päckchen AT) kann eine Schule eigene Rahmenwerke in der Bibliothek ablegen, etwa
die Nachhaltigkeitsziele (SDGs) oder das Weltethos. Im Curriculum verweisen Lehrkräfte darauf,
so wie auf eine Leitperspektive des Bildungsplans. Der Curriculum-Assistent kennt die
Leitlinien und trägt Aspekte ein.

## Zwei Typen, über Kürzel verbunden

| Typ | Was | Scopes | Embedding | Sammlung |
|---|---|---|---|---|
| `leitbild` | die Leitlinie („Nachhaltigkeitsziele“) | `school`/`school` | nein (Behälter) | ja, `schueler: false` |
| `leitbild_aspekt` | ein Punkt („SDG 13 Klimaschutz“) | `school`/`school` | ja | ja, `schueler: true` |

- **Kürzel:** Jeder Knoten trägt `metadata.kuerzel`. Es ist Pflicht und je Typ eindeutig
  (ohne Leerzeichen, in Großbuchstaben). Der Aspekt nennt seine Leitlinie in
  `metadata.leitlinie`, also über deren Kürzel. **Eine Kante gibt es dafür nicht.**
- **Prüfung:** `pruefe_leitlinie` in `app/context/leitlinien.py`, aufgerufen in
  `POST`/`PATCH /context/nodes`. Sie weist ab:
  - ein fehlendes oder doppeltes Kürzel;
  - einen Aspekt ohne vorhandene Leitlinie;
  - ein geändertes Kürzel einer Leitlinie, solange Aspekte es nennen.
- **Rechte:** Anlegen und Ändern nur mit Admin-Rolle (403 sonst, auch beim Umwandeln eines
  eigenen Bausteins). `write_scope: school` allein reichte nicht: Die Eigentümerin dürfte
  sonst ändern, und anlegen darf jede Lehrkraft.
- **Lesen:** alle Angemeldeten, auch Schüler:innen (`read_scope: school`). Über
  `collection.schueler` stehen die Aspekte in *Nachschlagen* der Gruppenseite und in der
  **Vorab-Suche** (`VORAB_TYPEN`). Die Sammlung ist fachunabhängig. `sammlungsAdresse` in
  `frontend/src/lib/collections.js` lässt deshalb das Fach aus der Adresse weg.
- **Nicht in „Alle Bausteine“:** beide Typen stehen in `bp_curriculum_content_types`.

## Verweise im Curriculum

Im Feld `hinweise` eines Eintrags stehen zwei neue Token, neben `lp`, `lpa` und `ik`:

```
@[<Label>](lb:<uuid>)    Leitlinie als Ganzes
@[<Label>](lba:<uuid>)   Aspekt einer Leitlinie
```

Wo sie gelesen werden — wer ein weiteres Token einführt, braucht dieselben Stellen:

| Ort | Was |
|---|---|
| `frontend/src/lib/hinweise.js` | Parser, Serializer, `extractEdgeTargets`, `leitlinienAuswahl` (Auswahl nach `@`) |
| `HinweisEditor.svelte`, `HinweisChip.svelte`, `CurriculumTable.svelte` | Auswahl und Anzeige (eigene Farbe `or`) |
| `routes/(app)/knowledge/curriculum/[id]/edit/+page.svelte` | Kanten `references` beim Speichern |
| `app/context/curriculum_export.py` | YAML: `lb:<kuerzel>`, `lba:<kuerzel>`; PDF und DOCX/ODT |
| `app/context/service.py` (`hinweise_code_to_uuid`, Import) | Kürzel → UUID; unbekannt → Text bleibt, Warnung |
| `app/context/curriculum_assistent.py` (`_HINWEIS_TOKEN`) | Kanten beim Schreiben des Assistenten |
| `app/context/curriculum_abdeckung.py` (`leitlinien_abdeckung`) | welche Aspekte in welchen Lernsequenzen vorkommen |

**Leitfaden Demokratiebildung (seit 0.53.1).** Ein eigenes Token gibt es nicht. `lpa:` zeigt
auch auf `lfdb_baustein`, `lfdb_themenblock` und `lfdb_kompetenz` (`LFDB_TYPEN` in
`app/context/leitlinien.py`). Parser, Anzeige, Kanten und PDF/DOCX liefen dadurch unverändert.
Geändert sind:

- **Auswahl:** `lfdbAuswahl` in `hinweise.js`. Ohne Suchtext nur Bausteine und Themenblöcke,
  mit Suchtext auch Kompetenzen; eingerückt nach Ebene (`tiefe`). Das Label lautet
  „LFDB B1.T2: <Titel>“ (`lfdbAnzeige`).
- **Import:** `resolve_leitperspektive_aspekt_node` nimmt die LFDB-Typen an. Der YAML-Export
  schreibt wie bei allen `lpa:` die `bp_id`.

## Curriculum-Assistent

Das Modell kennt keine UUIDs. Es schreibt Kürzel in zwei Felder der Operationen
`eintrag_anlegen` und `eintrag_aendern`:

- `leitlinien`: Kürzel (oder Titel) von Leitlinien und Aspekten;
- `leitperspektiven`: Kürzel einer Leitperspektive („BNE“) oder, im Curriculum der Regelfall,
  eines ihrer Aspekte („BNE_03“, die `bp_id` wie im YAML-Export). `lp_kuerzel_normalisieren`
  nimmt auch „BNE 3“, „bne3“ und „BNE-03“ an, `leitperspektiven_tokens` auch den Titel. Die
  Beschriftung des Tokens ist dieselbe wie aus dem Editor („BNE 3: <Titel>“).
  Für den Leitfaden Demokratiebildung gilt die Kurzform `LFDB_B1_T2` bzw. `LFDB_B1_T2_K3`
  (`lfdb_kuerzel`: die `bp_id` ab `LFDB_`). `lp_kuerzel_normalisieren` nimmt auch
  „LFDB B1.T2“ und „lfdb_b1_t2“ an.

Der Server macht daraus Token (`leitlinien_tokens`, `leitperspektiven_tokens`). Ein
unbekanntes Kürzel weist den Stapel ab und nennt die möglichen. Beim Lesen
(`get_curriculum_draft`) verschwinden die Token aus `hinweise` und stehen als Kürzel in
denselben Feldern. Dazu kommen:

- `leitperspektiven`: nur die Köpfe mit der Zahl ihrer Aspekte. Die Aspekte selbst (51)
  liefert `get_bp_competences` mit `typ='lp'` auf Abruf, sonst stünden sie bei jedem Lesen des
  Curriculums im Kontext. Mit `bereich='LFDB'` liefert sie den Baum des Leitfadens;
- `leitlinien_der_schule` mit ihren Aspekten (meist wenige);
- in `get_curriculum_coverage` je Leitlinie die nicht vorkommenden Aspekte.

**Genannte Felder ersetzen, andere bleiben:** Ein `eintrag_aendern` nur mit `hinweise`
behält die Verweise; eines mit `leitlinien` ersetzt nur diese.

## Schulweite Übersicht (seit 0.53)

Päckchen AU: Wo kommt welcher Aspekt einer Leitlinie **oder Leitperspektive** über alle
Curricula vor? Die Abdeckung oben zeigt das je Curriculum aus dem Baum; die Übersicht fragt
die Datenbank über alle Curricula, die die Person lesen darf.

**Abfrage** (`app/context/leitlinien_uebersicht.py`):

- `leitlinien_fundstellen(db, ziel_ids, user, nur_veroeffentlicht=False)` geht über die Kanten,
  nicht über die Token: `references` (Lernsequenz → Ziel), dann `part_of` Lernsequenz → Kapitel
  → Curriculum. Das gilt für `lb`/`lba` wie für `lp`/`lpa`, denn beide Wege legen beim
  Speichern dieselben Kanten an. Je Verweis eine Fundstelle mit Fach, Curriculum, Status,
  Fassung, Stufen, Kapitel und Lernsequenz.
- **Was zählt:**
  - Curricula mit `active` und, für alle mit `darf_entwurf_lesen`, `draft`.
  - Lesbar sind sie über `read_scope` `global`/`school`/`subject`, eigene `private` nur
    außerhalb der Vorschau (`eigenes_zaehlt`).
  - Kapitel und Lernsequenz zählen nur mit dem Status ihres Curriculums, ein archiviertes
    Kapitel also nicht.
  - Archivierte Aspekte fallen heraus.
- **Ersetzende Entwürfe:** Ein Entwurf mit `metadata.kopie_von` verdrängt sein Original — wie
  die Bandabdeckung mit Entwürfen. Sonst stünde dieselbe Lernsequenz zweimal im Raster. Mit
  `nur_veroeffentlicht` zählt nur `active`.
- `leitlinien_uebersicht(db, node_id, user, nur_veroeffentlicht=False)` baut daraus die Antwort
  und gibt `None` für alles, was keine aktive Leitlinie oder Leitperspektive ist. Der Baum
  entsteht je Art anders:

| Art | Aspekte | Kürzel des Aspekts |
|---|---|---|
| `leitbild` | `alle_leitlinien` (über `metadata.leitlinie`) | `metadata.kuerzel` |
| `leitperspektive` | `_leitperspektive`: `part_of`-Kanten der `leitperspektive_aspekt` | `metadata.bp_id` („BNE_07“) |
| `leitperspektive` mit Kürzel `LFDB` (seit 0.53.1) | `_lfdb`: Themenblöcke unter den Bausteinen, je `part_of` | „B1.T2“ (`lfdb_anzeige`) |

Beim LFDB fallen mehrere Ziele in eine Spalte. `_lfdb` liefert dazu die Zuordnung Ziel →
Spalte: eine Kompetenz zu ihrem Themenblock, Bausteine und der LFDB selbst zu `ganz`. Je
Spalte zählt eine Lernsequenz einmal, auch wenn sie auf Themenblock und Kompetenz verweist.

**Antwort:**

| Feld | Inhalt |
|---|---|
| `art` | `leitlinie` oder `leitperspektive` |
| `leitlinie` | `node_id`, `kuerzel`, `titel` |
| `nur_veroeffentlicht` | wahr auch dann, wenn die Person keine Entwürfe lesen darf |
| `aspekte` | je Aspekt `fundstellen` und `je_fach` (Fach-ID → Anzahl) |
| `ganz` | Fundstellen mit Verweis auf die Leitlinie als Ganzes, beim LFDB auch auf einen Baustein |
| `faecher` | Fächer mit mindestens einer Fundstelle |
| `alle_faecher` | alle Zeilen aus `subjects`, ungefiltert; Curricula ohne Fach als „ohne Fach“ am Ende |
| `ohne_fundstelle` | Kürzel der Aspekte ohne Fundstelle |

Beide Fächerlisten folgen `sort_order`, dann dem Namen, damit die Zeilen beim Umschalten an
ihrem Platz bleiben.

**Route:** `GET /context/leitlinien/{node_id}/uebersicht?nur_veroeffentlicht=` mit
`require_any_role(["teacher", "admin"])`. In der Vorschau trägt das Token die Rollen einer
Schüler:in, die Route antwortet dort also 403 — ohne eigenen Eintrag. Unbekannt oder kein
Rahmenwerk: 404.

**Wächter:** Beide Funktionen rufen `darf_entwurf_lesen` und stehen deshalb in `DIREKT` und
`LESEND` von `tests/unit/test_entwurf_leserecht_waechter.py`. Die Namen sind bewusst
eindeutig, weil der Wächter gleichnamige Funktionen zusammenfasst.

**Oberfläche:**

- **Seite:** `routes/(app)/knowledge/cross-cutting-themes/[id]/overview/+page.svelte`. Die
  Umformung steht in `frontend/src/lib/leitlinien_uebersicht.js` und ist ohne Oberfläche
  geprüft (`spalten`, `zeilen`, `stufenAuswahl`, `aufStufe`, `fundstelleHref`).
- **Filter in der Adresse:**
  - `faecher=alle`;
  - `nur_veroeffentlicht=1` — der einzige, der neu lädt;
  - `stufe=<n>` — wirkt nur im Frontend über `min_grade`/`max_grade` der Fundstellen. Ohne
    Stufenangabe fällt eine Fundstelle bei gewählter Klasse heraus.
- **Farben:** die Mengenstufen `--diagramm-stufe-1…5` der Heatmap (`lib/heatmap_stufen.js`).
  Die Zahl steht in Textfarbe neben dem Farbfeld, nicht darauf.
- **Sprung ans Kapitel:** Kapitelzeilen in `CurriculumTable.svelte` tragen
  `id="kapitel-<uuid>"`. Die Curriculum-Seite scrollt nach dem Laden zum Hash.

**Tests:**

- `tests/integration/test_leitlinien_uebersicht.py` prüft über die echte Kette:
  - ersetzende Kopie;
  - `nur_veroeffentlicht` und ohne Leserecht;
  - archivierte Teile;
  - Leitperspektive;
  - alle Fächer.
- `tests/unit/test_leitlinien_uebersicht_route.py` prüft die Rollen und die Vorschau.
- `frontend/src/lib/leitlinien_uebersicht.test.js` prüft das Raster und die Stufen.
