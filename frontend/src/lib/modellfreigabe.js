/**
 * Hinweis in der Modell-Freischaltung (0.51, Päckchen AV Schritt 8, F1).
 *
 * Die Prompts der Assistenten für Schüler:innen sind an wenigen Standardmodellen gemessen
 * (`SCHUELER_STANDARDMODELLE`, vom Server mit der Matrix geliefert). Bekommt ein Jahrgang ein
 * anderes Modell, sagt die Matrix das — gesperrt wird nichts, die Freigabe ist Sache der Schule.
 */

/**
 * Je abweichendem Modell die Jahrgänge, die es haben — nach dem **ungespeicherten** Stand.
 * Nur Modelle, die die Matrix zeigt (`modelle`): Eine Team-Liste kann noch Namen tragen, die
 * der Proxy nicht mehr kennt (etwa ein entferntes `ollama-fallback`) — die sind weder wählbar
 * noch nutzbar, ein Hinweis auf sie verwirrte nur.
 *
 * @param {Record<string, Set<string>>} auswahl  team_id → freigegebene Modelle
 * @param {string[]} standard
 * @param {string[] | null} modelle  die Modelle der Matrix; `null`: nicht einschränken
 * @returns {{modell: string, klassen: string[]}[]}
 */
export function abweichendeSchuelerModelle(auswahl, standard, modelle = null) {
  if (!standard?.length) return []
  const sichtbar = modelle ? new Set(modelle) : null
  const je = new Map()
  for (const [team, modelle] of Object.entries(auswahl ?? {})) {
    if (!team.startsWith('jahrgang-')) continue
    for (const m of modelle) {
      if (standard.includes(m) || (sichtbar && !sichtbar.has(m))) continue
      if (!je.has(m)) je.set(m, [])
      je.get(m).push(team.replace('jahrgang-', ''))
    }
  }
  return [...je.entries()]
    .map(([modell, klassen]) => ({ modell, klassen: klassen.sort((a, b) => a.localeCompare(b, 'de', { numeric: true })) }))
    .sort((a, b) => a.modell.localeCompare(b.modell))
}

/** Der Satz für den Hinweis, oder `null`. */
export function hinweisSchuelerModelle(auswahl, standard, modelle = null) {
  const abweichend = abweichendeSchuelerModelle(auswahl, standard, modelle)
  if (!abweichend.length) return null
  const liste = abweichend.map((a) => `${a.modell} (Klasse ${a.klassen.join(', ')})`).join('; ')
  return `Für Schüler:innen freigegeben, aber kein Standardmodell: ${liste}. Die Assistenten für ` +
    `Schüler:innen sind an ${standard.join(', ')} gemessen; mit einem anderen Modell halten sie ` +
    'sich womöglich nicht an ihre Regeln (etwa „nichts vorsagen“).'
}
