/**
 * Abdeckung eines Curriculums (0.45, Päckchen AP Teil A) — Texte und Filter für
 * `CurriculumAbdeckung.svelte`. Die Zahlen rechnet das Backend (`/coverage`).
 */

/** Kopfzeile der aufklappbaren Übersicht. */
export function abdeckungUeberschrift(a) {
  if (!a) return 'Abdeckung'
  const ik = a.ik
  if (!ik.gesamt) return 'Abdeckung: keine Kompetenzen des Bands gefunden'
  const teile = [`Abdeckung: ${ik.verknuepft} von ${ik.gesamt} IK verknüpft`]
  if (ik.partiell) teile.push(`${ik.partiell} partiell`)
  if (ik.fehlt) {
    teile.push(
      ik.fehlt_anderswo
        ? `${ik.fehlt} fehlen (${ik.fehlt_anderswo} davon in anderen Curricula des Bands)`
        : `${ik.fehlt} fehlen`,
    )
  }
  teile.push(`PK ${a.pk.genutzt} von ${a.pk.gesamt} gefördert`)
  if (a.fremdes_fach?.length) teile.push(`⚠ ${a.fremdes_fach.length} aus einem anderen Fach`)
  return teile.join(' · ')
}

/** Gruppen mit den Kompetenzen, die der Filter zeigt; leere Gruppen fallen weg. */
export function gefilterteGruppen(gruppen, nurLuecken) {
  return (gruppen || [])
    .map((g) => ({
      ...g,
      kompetenzen: nurLuecken ? g.kompetenzen.filter((k) => k.zustand !== 'verknuepft') : g.kompetenzen,
    }))
    .filter((g) => g.kompetenzen.length)
}

export const ZUSTAND = {
  verknuepft: { text: 'verknüpft', klasse: 'text-light-gr dark:text-dark-gr' },
  partiell: { text: 'partiell', klasse: 'text-light-ye dark:text-dark-ye' },
  fehlt: { text: 'fehlt', klasse: 'text-light-re dark:text-dark-re' },
}
