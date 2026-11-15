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
