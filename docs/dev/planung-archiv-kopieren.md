# Planung: Archiv, Rechte, Kopieren und Einheitenansicht (0.42)

Seit 0.42 hat die Unterrichtsplanung einen eigenen Menüpunkt „Planung“: je aktuelle Gruppe ein
Link in ihren Planer, darunter das Archiv früherer Schuljahre. Seit 0.42.2 öffnet der Menükopf die
Übersicht `/planning` mit denselben Gruppen als Kacheln (Beschriftung `menueBeschriftung`, Quelle
`GET /planning/groups`) und dem Archiv abgesetzt darunter. Seit 0.42.3 zeigt der Planer neben der
Jahresübersicht die Einheiten mit ihren Stunden, auch denen ohne Termin. Diese Seite beschreibt, wer was
sieht und ändern darf und was eine Kopie mitnimmt. Die Regeln stehen ausführlich in den
Moduldocstrings; hier steht, wo sie liegen und warum sie so sind.

## Welche Gruppe ist „aktuell“?

`app/groups/aktualitaet.py` entscheidet für Menü, `/groups/me` und Archiv gleich: SSO-Gruppen
und Gruppen ohne Quellklasse sind aktuell, sonst zählt ein **Beleg** im laufenden Schuljahr
(Termine oder Planung) oder das Anlegedatum nach Schuljahresbeginn. `gruppe_ist_aktuell(db, gruppe)`
fragt das für eine einzelne Gruppe.

⚠️ **Schuljahr der Planungsknoten:** Die Spalte `context_nodes.schuljahr` füllt kein
Erzeugungsweg; das Schuljahr steht in `metadata.schuljahr` (Jahresplan, Einheit). Abfragen nehmen
deshalb `schuljahr_des_knotens()` (Coalesce aus beidem). Bis 0.42 lasen `gruppen_mit_beleg` und
`letztes_schuljahr` nur die Spalte und fanden nie etwas.

Folge, gewollt: Öffnet jemand den Planer einer früheren Gruppe, legt der Planer einen
Jahresplan des laufenden Jahres an — die Gruppe gilt dann wieder als aktuell.

## Lesen und Ändern

Eine Regel, eine Stelle: `app/planning/permissions.zugang_zur_stunde` (gilt für Einheiten
genauso).

| Lage | Ergebnis |
|---|---|
| Lehrkraft der Gruppe, Knoten `active`, Gruppe aktuell | lesen und ändern |
| Lehrkraft der Gruppe, sonst | nur lesen |
| Eigentümer:in ohne Mitgliedschaft | nur lesen |
| sonst | 403 |

Lesende Routen (`GET /planning/lessons/{id}`, Export) nehmen `active` und `archived`
(`LESBAR` im Router); schreibende prüfen über `_darf_stunde_aendern` und antworten mit 403.
Die Oberfläche richtet sich nach `darf_bearbeiten` in der Antwort. Planer, Termine und
Nachbereitung einer nicht mehr aktuellen Gruppe bleiben für Mitglieder bewusst schreibbar
(`require_group_teacher`) — gesperrt ist der Stundenentwurf.

## Archiv

`app/planning/archiv.py`, Routen `GET /planning/archive` und `GET /planning/archive/groups/{id}`,
in fester Zahl von Abfragen.

- **Zugang `mitglied`:** Gruppe nicht aktuell, ich bin noch Lehrkraft — alles der Gruppe.
- **Zugang `eigentum`:** keine Mitgliedschaft mehr, aber eigene Planung — nur Eigenes; eine
  fremde Einheit mit eigenen Stunden erscheint mit diesen.
- Stunden in `follows`-Reihenfolge (`_ordne`), Einheiten nach erstem Termin. Gruppen ohne
  Inhalt fallen weg; gruppenlose Knoten (Gruppe gelöscht, `write_scope_group_id` NULL)
  erscheinen nicht.

## Kopieren

`app/planning/kopieren.py`, Routen `POST /planning/lessons/{id}/copy`
(`{gruppe_id, einheit_id | neue_einheit}`) und `POST /planning/units/{id}/copy` (`{gruppe_id}`).
Antwort mit `meldungen`: was weggelassen oder umgestellt wurde.

- **Quelle:** lesbar nach `zugang_zur_stunde`, `active` oder `archived`. Bei einer Einheit
  genügen auch eigene Stunden darin (wie im Archiv); kopiert werden die lesbaren Stunden.
- **Ziel:** Lehrkraft dort (403), Gruppe aktuell und dasselbe Fach (422); bei der Stunde genau
  eins von bestehender Einheit der Zielgruppe oder Titel einer neuen.
- **Felder:** Phasen nur mit den Schemafeldern von `LessonPhaseItem` und neuen Kennungen — was
  Nachbereitung, Kürzen und Übertragen in eine Phase schreiben, bleibt bei der gehaltenen
  Stunde. Nicht übernommen: Termin, `refs_dismissed`, `refs_offen`, `begriffe_vorschlag`,
  `reflexion`, `assistant_id`. Herkunft in `metadata.kopie_von`.
- **Kompetenzen:** in der Fassung, die für die Zielgruppe gilt (`aktive_bp_version` je Fach und
  Art, wie die Suche). Weicht sie ab, wird auf den Zwilling umgestellt — gleiche Nummer, Text
  weitgehend gleich, dieselbe Regel wie das Curriculum-Relinking (`relink._twin_map`/`_decide`).
  Ohne bestimmbaren Jahrgang bleiben die Verweise.
- **Material und Begriffe:** nur, wenn die Zielgruppe sie lesen kann (offener Scope, Scope der
  Zielgruppe, eigenes Privates).
- **Kapitel einer Einheit:** nur, wenn das Kapitel in einem Curriculum der Zielgruppe liegt.
- **Nachbereitungsnotiz:** als `metadata.notiz_aus_vorlage = {text, kopie_von, datum}` —
  nicht als `reflexion`, also nicht im Vektor und keine Nachbereitung. Die Kopie einer Kopie
  reicht die geerbte Notiz unverändert weiter. Entfernen: `PATCH … {notiz_aus_vorlage_entfernen: true}`.
- **Transaktion:** Die Funktionen committen nicht. Eine Einheit entsteht ganz oder gar nicht;
  die neuen Stunden folgen einander über die durchgereichte Vorgängerin, weil alle dieselbe
  Anlegezeit tragen.

Der allgemeine Kopierweg `POST /context/nodes/{id}/copy` lehnt Planungsknoten mit 422 ab — es
gibt einen Weg, nicht zwei.

## Einheitenansicht und Einplanen (0.42.3)

Eine Stunde erscheint in der Jahresübersicht nur über einen Termin (`lesson_slots.stunde_node_id`).
Eine Kopie — oder eine Stunde, die über `POST /planning/units/{id}/lessons` ohne `slot_id` entsteht —
hängt nur per `part_of` an ihrer Einheit. Damit sie nicht verloren geht, hat der Planer eine zweite
Ansicht:

- **Daten:** `GET /planning/groups/{id}/inhalt` (`require_group_teacher`) — dieselbe Aufbereitung wie
  das Archiv (`archiv.archiv_inhalt`, Antwort `ArchivInhaltRead`, gemeinsam über `_inhalt_read`), aber
  nur `active` (`stati=("active",)`), wie die Jahresübersicht. Je Stunde `slot_id`; `None` heißt
  „ohne Termin“. Das Archiv liefert das Feld mit.
- **Ansicht:** `?ansicht=jahr|einheiten` (dazu `?einheit=`) am Planer; ohne Angabe gilt die
  Einstellung `planung_ansicht` (je Nutzer). Kachel auf `/planning`, Menü und Rückweg aus dem
  Stundenentwurf brauchen deshalb keine eigenen Links. Darstellung: `EinheitenAnsicht.svelte`,
  gemeinsam mit der Archivseite; Hilfen in `lib/planung_archiv.js`.
- **Einplanen:** kein eigener Endpunkt, sondern `PATCH /planning/slots/{id}` mit `stunde_node_id`,
  `expected_updated_at` und — wenn der Termin keine trägt — `ue_node_id`. Auswahl und Anfrage:
  `lib/einplanen.js` (Unterricht, ohne Entwurf, ab heute; Termine der Einheit zuerst, dann leere;
  andere Einheiten nicht).

⚠️ **Die Einheit gehört in die Anfrage.** `ordne_entwurf_ein` hängt den Entwurf an die Einheit **des
Termins**. Trägt der Termin keine, fällt die `part_of`-Kante der Stunde weg — sie stünde danach
„ohne Einheit“ (`test_einplanen_ohne_einheit_am_termin_loeste_die_stunde`). Ob andere Aufrufer
(Planungsassistent) denselben Fall erzeugen, ist als Todo offen.

⚠️ **Frei prüft der Server nicht.** `PATCH /slots/{id}` überschreibt einen Entwurf am Termin; die
Auswahl bietet nur Termine ohne Entwurf an, und `expected_updated_at` lehnt einen inzwischen
geänderten Termin mit 409 (`grund: veraltet`) ab.

## „Meine Bausteine“

Planungstypen sind persönlich gepflegt (`PERSOENLICHE_CONTENT_TYPES`), stehen aber nicht in
„Meine Bausteine“: `meine_bausteine._eigener_bestand` schließt `PLANUNG_CONTENT_TYPES` aus —
für Liste, Typfilter und Aufmerksamkeitszähler. „Eingesetzt in“ am Material bleibt.

## Tests

`tests/integration/test_planung_archiv.py`, `test_planung_kopieren.py`,
`test_planung_einheitenansicht.py`, `test_meine_bausteine.py`; Frontend `planung_archiv.test.js`,
`planung_kopieren.test.js`, `einplanen.test.js`.
