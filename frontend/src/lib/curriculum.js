export function lernsequenzStd(ls) {
    const v = Number(ls?.metadata?.std)
    return Number.isFinite(v) ? v : 0
}

export function kapitelStd(kap) {
    return (kap?.lernsequenzen || []).reduce((s, ls) => s + lernsequenzStd(ls), 0)
}

export function curriculumStd(curr) {
    return (curr?.kapitel || []).reduce((s, k) => s + kapitelStd(k), 0)
}

/** Hinweis im Kopf von Ansicht und Editor eines Entwurfs (0.45, Päckchen AP). */
export const ENTWURF_HINWEIS =
  'Entwurf: Nur die Fachschaft und Admins sehen dieses Curriculum. In Suche, Chat und Jahresplanung erscheint es erst nach dem Veröffentlichen.'

/**
 * Banner in der Planung (0.45, E15): Einheiten, deren Curriculum-Kapitel zu einem ersetzten
 * (archivierten) Curriculum gehört. `titel`: die Titel der eigenen Einheiten.
 */
export function ersetztHinweis(titel) {
  if (!titel?.length) return ''
  const welche = titel.length === 1 ? `Die Einheit „${titel[0]}“ hängt` : `${titel.length} Einheiten (${titel.map((t) => `„${t}“`).join(', ')}) hängen`
  return `${welche} an einem Kapitel eines Curriculums, das inzwischen ersetzt wurde. Wähle unter „Einheit bearbeiten“ ein Kapitel des neuen Curriculums.`
}
