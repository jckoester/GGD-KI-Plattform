/**
 * Hilfsfunktionen für die Operatoren-Anzeige im Bildungsplan-View.
 *
 * Operatoren (handlungsleitende Verben) werden tabellarisch nach Titel gesucht,
 * daher alphabetisch sortiert — locale-aware ('de'), damit Umlaute korrekt
 * einsortiert werden (ä≈a, ö≈o, ü≈u, ß), z. B. "überprüfen" nicht ans Ende.
 */

/**
 * Sortiert Operator-Knoten alphabetisch nach Titel (deutsche Sortierung).
 * Reine Funktion — mutiert die Eingabe nicht.
 *
 * @param {Array<{title?: string}>} operators
 * @returns {Array} neue, sortierte Liste
 */
export function sortOperatorsByTitle(operators) {
  return [...(operators ?? [])].sort((a, b) =>
    (a?.title || '').localeCompare(b?.title || '', 'de'),
  )
}

/**
 * Formatiert die AFB-Zuordnung eines Operators als Anzeigetext ("II" bzw. "I, II").
 * @param {{metadata?: {afb?: string[]|string}}} op
 * @returns {string}
 */
export function formatAfb(op) {
  const afb = op?.metadata?.afb
  if (Array.isArray(afb)) return afb.join(', ')
  return afb ? String(afb) : ''
}
