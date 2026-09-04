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
