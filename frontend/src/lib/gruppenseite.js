/**
 * Die Regeln der Unterrichtsgruppen-Seite — ohne Markup.
 *
 * Dieselbe Seite bedient beide Rollen: Was eine Schüler:in „mein Fach Mathematik"
 * nennt, ist im Datenmodell die Unterrichtsgruppe — genau das, was die Lehrkraft
 * „Klasse 8c" nennt. Was sich zwischen den Rollen unterscheidet, ist keine andere
 * Seite, sondern ein Sichtbarkeitsschalter.
 *
 * Hier steht nur, was sich ohne Browser prüfen lässt; das Projekt hat keine
 * Komponententests.
 */

/**
 * Die Reiter der Lehrkraft-Ansicht, in Anzeigereihenfolge.
 *
 * Schüler:innen sehen **keine** Reiter — für sie gibt es nur die Übersicht.
 * `klasse` ist im September 2026 entfallen: Was der Reiter versprach (Freigabe und
 * Sichtbarkeitsfenster je Gruppe), liegt längst am Assistenten selbst
 * (`scope_group_id`, `available_from`, `available_until`). Ein Reiter, der
 * Vorhandenes ankündigt, ist schlimmer als keiner.
 */
export const REITER = [
  { id: 'uebersicht', label: 'Übersicht' },
  { id: 'curriculum', label: 'Curriculum' },
  { id: 'bildungsplan', label: 'Bildungsplan' },
  { id: 'archiv', label: 'Archiv' },
  { id: 'kontext', label: 'weiterer Kontext' },
]

/**
 * Kennungen, die es einmal gab und die in Lesezeichen stehen.
 *
 * Bis 09/2026 hieß die Übersicht `vorbereitung`. Die Kennung steht in gespeicherten
 * Links; sie fallen zu lassen hieße, dass ein Lesezeichen wortlos auf einer leeren
 * Seite landet — der Reiter-Zustand kommt aus der URL, ein unbekannter Wert trifft
 * dann keinen Zweig.
 */
const ALTE_KENNUNGEN = {
  vorbereitung: 'uebersicht',
}

const GUELTIG = new Set(REITER.map((r) => r.id))

/**
 * Welcher Reiter zu einem `?tab=`-Wert gehört.
 *
 * Unbekannte und fehlende Werte fallen auf die Übersicht zurück — sie ist die
 * Antwort auf „wo war ich stehengeblieben?", also der richtige Ort für jemanden,
 * der aus Versehen hier gelandet ist.
 *
 * @param {string|null|undefined} roh  der Wert aus der Adresszeile
 * @returns {string} eine Kennung aus {@link REITER}
 */
export function aktiverReiter(roh) {
  if (!roh) return 'uebersicht'
  const uebersetzt = ALTE_KENNUNGEN[roh] ?? roh
  return GUELTIG.has(uebersetzt) ? uebersetzt : 'uebersicht'
}
