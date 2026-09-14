/**
 * Konkrete Termine eines Wochenmusters — A-/B-Wochen greifbar machen.
 *
 * Der Buchstabe allein hilft nicht: Heißt eine Woche im Stundenplan der Schule anders als
 * hier, vergleicht die Lehrkraft Bezeichnungen und korrigiert im Zweifel das Auswahlfeld —
 * womit sich die Phase um eine Woche verschiebt. Neben konkreten Daten ist der Buchstabe
 * dagegen belanglos.
 *
 * Gerechnet wird nicht: `GET /planning/ab-wochen` liefert die Schultage des Halbjahres
 * bereits nach Phase getrennt, Feiertage inklusive. Hier wird nur nach Wochentag gefiltert
 * und formatiert — ein zweiter Schulkalender im Browser könnte vom ersten abweichen.
 */

/** Wochentag eines ISO-Datums, 0 = Montag (`Date.getDay()` zählt ab Sonntag). */
function wochentag(iso) {
  const [jahr, monat, tag] = iso.split('-').map(Number)
  return (new Date(jahr, monat - 1, tag).getDay() + 6) % 7
}

/** `2026-06-15` → `15.06.` */
export function kurzdatum(iso) {
  const [, monat, tag] = iso.split('-')
  return `${tag}.${monat}.`
}

/**
 * Die nächsten Termine eines Musters.
 *
 * @param kalender  Antwort von `GET /planning/ab-wochen` (oder `null`, solange sie fehlt)
 * @param weekday   0 = Montag
 * @param rhythmus  `woechentlich` | `a_woche` | `b_woche`
 * @param ab        ISO-Datum; frühere Termine werden übergangen (Vorgabe: alle)
 * @returns `{ daten: string[], gesamt: number }` — formatierte Kurzdaten und wie viele
 *          Termine es insgesamt gibt. Leer, solange der Kalender fehlt.
 */
export function termine(kalender, weekday, rhythmus, { ab = null, anzahl = 4 } = {}) {
  if (!kalender || rhythmus === 'woechentlich') return { daten: [], gesamt: 0 }
  const tage = kalender[rhythmus]
  if (!Array.isArray(tage)) return { daten: [], gesamt: 0 }
  const passend = tage.filter(
    (iso) => wochentag(iso) === Number(weekday) && (!ab || iso >= ab),
  )
  return { daten: passend.slice(0, anzahl).map(kurzdatum), gesamt: passend.length }
}

/** Die Zeile unter dem Auswahlfeld — leer, wenn es nichts zu zeigen gibt. */
export function terminzeile(kalender, weekday, rhythmus, optionen = {}) {
  const { daten, gesamt } = termine(kalender, weekday, rhythmus, optionen)
  if (!daten.length) return ''
  return gesamt > daten.length ? `${daten.join(' · ')} · …` : daten.join(' · ')
}
