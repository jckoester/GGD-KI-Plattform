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

## Curriculum-Assistent

Das Modell kennt keine UUIDs. Es schreibt Kürzel in zwei Felder der Operationen
`eintrag_anlegen` und `eintrag_aendern`:

- `leitlinien`: Kürzel (oder Titel) von Leitlinien und Aspekten;
- `leitperspektiven`: Kürzel einer Leitperspektive („BNE“) oder, im Curriculum der Regelfall,
  eines ihrer Aspekte („BNE_03“, die `bp_id` wie im YAML-Export). `lp_kuerzel_normalisieren`
  nimmt auch „BNE 3“, „bne3“ und „BNE-03“ an, `leitperspektiven_tokens` auch den Titel. Die
  Beschriftung des Tokens ist dieselbe wie aus dem Editor („BNE 3: <Titel>“).

Der Server macht daraus Token (`leitlinien_tokens`, `leitperspektiven_tokens`). Ein
unbekanntes Kürzel weist den Stapel ab und nennt die möglichen. Beim Lesen
(`get_curriculum_draft`) verschwinden die Token aus `hinweise` und stehen als Kürzel in
denselben Feldern. Dazu kommen:

- `leitperspektiven`: nur die Köpfe mit der Zahl ihrer Aspekte. Die Aspekte selbst (51)
  liefert `get_bp_competences` mit `typ='lp'` auf Abruf, sonst stünden sie bei jedem Lesen des
  Curriculums im Kontext;
- `leitlinien_der_schule` mit ihren Aspekten (meist wenige);
- in `get_curriculum_coverage` je Leitlinie die nicht vorkommenden Aspekte.

**Genannte Felder ersetzen, andere bleiben:** Ein `eintrag_aendern` nur mit `hinweise`
behält die Verweise; eines mit `leitlinien` ersetzt nur diese.
