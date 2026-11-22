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

/**
 * Hinweis im Kopf von Ansicht und Editor eines Entwurfs (0.45, Päckchen AP). Seit 0.52 (AZ)
 * lesen alle Lehrkräfte Entwürfe; der Satz sagt das der Fachschaft, die ihn bearbeitet (F2).
 */
export const ENTWURF_HINWEIS =
  'Entwurf: Alle Lehrkräfte können ihn lesen, bearbeiten kann ihn die Fachschaft. In Suche, Chat und Jahresplanung erscheint er erst nach dem Veröffentlichen.'

/** Dasselbe für Lehrkräfte, die den Entwurf nur lesen (0.52, AZ). */
export const ENTWURF_NUR_LESEN =
  'Entwurf — nur lesen. Bearbeiten und veröffentlichen kann die Fachschaft des Fachs. Noch nicht gültig: In Suche, Chat und Jahresplanung erscheint er erst nach dem Veröffentlichen.'

/** Welcher der beiden Hinweise zu einem Curriculum gehört; leer, wenn es kein Entwurf ist. */
export function entwurfHinweis(curriculum) {
  if (curriculum?.status !== 'draft') return ''
  return curriculum.can_edit ? ENTWURF_HINWEIS : ENTWURF_NUR_LESEN
}

/**
 * Banner in der Planung (0.45, E15): Einheiten, deren Curriculum-Kapitel zu einem ersetzten
 * (archivierten) Curriculum gehört. `titel`: die Titel der eigenen Einheiten.
 */
export function ersetztHinweis(titel) {
  if (!titel?.length) return ''
  const welche = titel.length === 1 ? `Die Einheit „${titel[0]}“ hängt` : `${titel.length} Einheiten (${titel.map((t) => `„${t}“`).join(', ')}) hängen`
  return `${welche} an einem Kapitel eines Curriculums, das inzwischen ersetzt wurde. Wähle unter „Einheit bearbeiten“ ein Kapitel des neuen Curriculums.`
}

/**
 * Beschriftungen toter Verweise (0.45): zu jeder Kennung die Beschriftung aus Hinweisen und
 * Material (`#[PH 3.4.3](ik:…)`, `@[…](lp:…)`), sonst die Kennung — je Verweis einmal.
 */
export function toteVerweiseBeschriftungen(curr, ids) {
  if (!ids?.length) return []
  const texte = []
  for (const k of curr?.kapitel || []) {
    for (const ls of k.lernsequenzen || []) {
      for (const e of ls.metadata?.eintraege || []) texte.push(e.hinweise || '', e.material || '')
    }
  }
  const spalten = new Map()
  for (const k of curr?.kapitel || []) {
    for (const ls of k.lernsequenzen || []) {
      for (const e of ls.metadata?.eintraege || []) {
        for (const r of [...(e.ik || []), ...(e.pk || [])]) {
          if (r?.node_id) spalten.set(r.node_id, r.nr || r.pk_id || r.node_id)
        }
      }
    }
  }
  const alles = texte.join('\n')
  return ids.map((id) => {
    const m = alles.match(new RegExp(`\\[([^\\]]*)\\]\\([a-z]+:${id}\\)`))
    return m ? m[1] : spalten.get(id) || id
  })
}
