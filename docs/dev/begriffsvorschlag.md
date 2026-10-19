# Begriffsvorschlag aus den Phasentexten (seit 0.18)

Die Leiste „Kompetenzen und Fachbegriffe" schlägt die Fachbegriffe einer Stunde vor. Ein
eigener kleiner Modellaufruf bestimmt sie aus den Phasentexten — unabhängig vom Modell des
Stundenassistenten. Code: `app/planning/begriffe.py`, `app/litellm/einzelaufruf.py`,
Frontend `BegriffVorschlag.svelte`.

## Ablauf

1. **Auslöser:** nach jedem erfolgreichen `update_lesson_phases` im Hintergrund
   (`im_hintergrund`, eigene Sitzung) und über den Knopf
   (`POST /planning/lessons/{id}/begriffe-vorschlagen?erzwingen=`).
2. **Eingabe:** der Entwurfstext (`entwurfstext`: Titel, Stundenziel, eine Zeile je Phase wie
   `phase_kurz`), die Begriffe früherer Stunden der Gruppe (`fruehere_begriffe`: Termine vor
   diesem, je Knoten einmal) und 5 Kandidaten nach Vektor (nur Lesbares). Anleitung
   `ANLEITUNG` — **wörtlich die des Vorlaufs**; ein Test hält ihre Prüfsumme fest.
3. **Aufruf:** `einzelaufruf` über den virtuellen Schlüssel der Lehrkraft (Budget, Abrechnung),
   JSON-Modus, Zeitlimit 45 s. Fehlerarten statt Ausnahmen: `kein_modell`, `kein_schluessel`,
   `budget`, `zeit`, `abgelehnt`.
4. **Abgleich:** wie das Werkzeug (`begriff_zum_titel`: Titel, Alias, Einzahl; Fach und
   Bezugsfächer). Einteilung in `eintraege` (neu), `frueher` (getrennt, nicht verworfen) und
   `ohne_knoten`; was in `refs` oder `refs_dismissed` steht, fehlt.
5. **Ablage:** `metadata.begriffe_vorschlag` per `jsonb_set` mit `ohne_aenderungsstempel()`.

## Fallen

- **`updated_at` bleibt stehen.** Der Aufruf dauert Sekunden. Ein neuer Stempel ließe den
  nächsten Speichervorgang im Editor ins optimistische Sperren laufen (409); das ganze
  Metadaten-Objekt zurückzuschreiben überschriebe, was die Lehrkraft inzwischen gespeichert
  hat.
- **Prüfsumme statt Zeitstempel.** Ein Vorschlag gilt, solange `pruefsumme(entwurfstext(...))`
  passt; dann läuft kein neuer Aufruf (außer `erzwingen`). Die Leiste zeigt „Entwurf geändert".
- **Werkzeugtexte überstimmen den Prompt.** Die Anleitung im Ergebnis von `get_lesson_detail`
  (`BEGRIFFE_ANLEITUNG`) kommt nach dem System-Prompt. Solange sie den alten Absatz „Begriffe
  dieser Stunde" verlangte, schrieb das Modell ihn trotz neuem Prompt. Wächter:
  `test_werkzeugtexte_folgen_dem_prompt`.
- **„Früher" ist kein Lernstand.** Nirgends „bekannt" sagen; Assistent und Leiste tragen
  `HINWEIS_FRUEHER`.
- **Tests:** Beide `conftest.py` setzen `begriffe_model` leer — steht es in der lokalen `.env`,
  löste sonst jedes `update_lesson_phases` im Test einen echten Aufruf aus.

## Konfiguration

`BEGRIFFE_MODEL` (leer = keine Vorschläge), Alias `system-begriffe` in der LiteLLM-Config, nur
für Lehrkräfte freigeschaltet. Gemessen und gewählt: Mistral Small mit 5 Kandidaten (Plan
„Begriffe aus den Phasentexten", § 9). Wer Modell, Anleitung oder Kandidatenzahl ändert, misst
neu — `Messungen-0.18/vorlauf/experiment.py` bzw. die Kriterien aus § 16.
