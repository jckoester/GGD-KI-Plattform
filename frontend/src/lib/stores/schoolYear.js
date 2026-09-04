/**
 * Das laufende Schuljahr aus `config/school_year.yaml` (`GET /calendar/school-year`).
 *
 * **Warum überhaupt geladen.** Der Knopf „Schuljahresende" im Baustein-Formular leitete
 * das Datum aus dem eingetippten Schuljahr ab und nahm dafür **fest den 31.07.** an — in
 * der Config steht der 29.07.2026 bzw. der 28.07.2027. Zwei Tage daneben fällt niemandem
 * auf, und genau deshalb blieb es stehen. Wichtiger als die zwei Tage ist der Gleichlauf:
 * Dasselbe Datum trägt der Server ein, wenn beim Anlegen kein Ablaufdatum angegeben wird.
 * Knopf und Automatik müssen dieselbe Antwort geben.
 *
 * `null` heißt „noch nicht beantwortet" — nicht „kein Schuljahr". Wer den Knopf zeigt,
 * prüft auf einen Wert; ein erfundenes Ersatzdatum wäre schlimmer als kein Knopf.
 */
import { writable, derived } from "svelte/store"
import { getSchoolYear } from "$lib/api.js"

const _schoolYear = writable(null)

/** `{schuljahr, beginn, ende, halbjahreswechsel}` oder `null`. */
export const schoolYear = derived(_schoolYear, ($s) => $s)

/** Das Ende als ISO-Datum (`2027-07-28`) oder `null`. */
export const schuljahresEnde = derived(_schoolYear, ($s) => $s?.ende ?? null)

let laeuft = null

/**
 * Lädt einmal je Sitzung. Mehrfachaufrufe teilen sich dieselbe Anfrage — zwei Formulare
 * auf demselben Weg sollen nicht zweimal fragen.
 */
export async function ladeSchuljahr() {
  if (laeuft) return laeuft
  laeuft = getSchoolYear()
    .then((daten) => {
      _schoolYear.set(daten)
      return daten
    })
    .catch(() => {
      // Bei Netzwerkfehler bleibt es bei `null`: Der Knopf erscheint dann nicht, das
      // Datumsfeld lässt sich weiterhin von Hand füllen.
      laeuft = null
      return null
    })
  return laeuft
}

/** `2027-07-28` → `28.07.` — für die Beschriftung des Knopfes. */
export function alsTagMonat(iso) {
  if (!iso) return ""
  const [, monat, tag] = iso.split("-")
  return `${tag}.${monat}.`
}

/**
 * Das Anfangsjahr einer Schuljahresangabe, oder `null`.
 *
 * ⚠️ **Zwei Schreibweisen im Umlauf, und sie sind nicht gleich.** Die Config schreibt
 * `2025/26`, die Formularvorgabe `2026/2027`. Ein Stringvergleich wäre also immer
 * ungleich — und der Knopf verschwände auf Dauer, ohne dass jemand den Grund sähe. Das
 * Anfangsjahr ist in beiden Formen dasselbe und das Einzige, was sich vergleichen lässt.
 */
function startjahr(angabe) {
  const treffer = /^(\d{4})/.exec((angabe ?? "").trim())
  return treffer ? Number(treffer[1]) : null
}

/**
 * Bezieht sich der Knopf auf dasselbe Schuljahr wie das Formular?
 *
 * Der Knopf liefert immer das Ende des **laufenden** Schuljahres — die Config kennt nur
 * eines. Trägt das Formularfeld „Schuljahr" ein anderes, setzte er kommentarlos ein
 * Datum aus einem fremden Jahr; dann erscheint er gar nicht erst.
 *
 * Aus dem eingetippten Jahr ein Datum zu rechnen wäre **kein** Ausweg: Das Ende eines
 * künftigen Schuljahres hängt an den Sommerferien und steht nirgends fest (29.07.2026,
 * 28.07.2027). Es zu berechnen hieße, den Tag zu raten — derselbe Fehler wie der früher
 * fest angenommene 31.07., nur mit einer anderen Konstante.
 *
 * Ein **leeres** Feld ist kein Widerspruch: Wer kein Schuljahr angibt, bekommt den Knopf.
 */
export function passtZumSchuljahr(feldwert, sj) {
  const config = startjahr(sj?.schuljahr)
  if (config === null) return false
  const eingetragen = startjahr(feldwert)
  return eingetragen === null || eingetragen === config
}
