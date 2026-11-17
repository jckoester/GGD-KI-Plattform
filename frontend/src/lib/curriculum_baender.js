/**
 * Curricula nach Fassung und Band des Bildungsplans (0.46, Päckchen AP Teil B, Schritt 8).
 *
 * Reine Hilfen für die Liste (`CurriculumList`) und die Abdeckung über das Band
 * (`/knowledge/curricula/coverage`). Die Struktur liefert das Backend
 * (`GET /context/curricula/by-subject/{id}/overview`).
 */

export const FASSUNG_ART = {
  geltend: '',
  kommend: 'kommende Fassung',
  aelter: 'frühere Fassung',
}

/** „BP 2016.V3“, bei kommenden und früheren Fassungen mit Zusatz. */
export function fassungTitel(fassung) {
  const zusatz = FASSUNG_ART[fassung?.art] ?? ''
  return `BP ${fassung?.bp_version ?? '?'}${zusatz ? ` · ${zusatz}` : ''}`
}

/** Pfad der Abdeckungsseite: mit `band` die IK des Bands, ohne die PK der Fassung (Schritt 9). */
export function abdeckungsPfad({ fachId, fassung, band = null, entwuerfe = false }) {
  const q = new URLSearchParams({ fach: String(fachId), fassung })
  if (band) q.set('band', band)
  if (entwuerfe) q.set('entwuerfe', '1')
  return `/knowledge/curricula/coverage?${q}`
}

/**
 * Was die Liste zeigt: Wer Curricula anlegen darf, sieht auch leere Bänder (dort fehlt noch
 * eines); alle anderen nur Bänder mit Curricula und nur Fassungen, in denen es welche gibt.
 */
export function sichtbareFassungen(uebersicht, { leereBaender = false } = {}) {
  return (uebersicht?.fassungen ?? [])
    .map((f) => ({
      ...f,
      baender: leereBaender ? f.baender : f.baender.filter((b) => b.curricula.length > 0),
    }))
    .filter((f) => leereBaender
      ? f.art !== 'aelter' || f.baender.some((b) => b.curricula.length) || f.nicht_zugeordnet.length
      : f.baender.length > 0 || f.nicht_zugeordnet.length > 0)
}

/** Anzahl der Curricula einer Fassung (für den eingeklappten Kopf älterer Fassungen). */
export function anzahlCurricula(fassung) {
  return (fassung?.baender ?? []).reduce((n, b) => n + b.curricula.length, 0)
    + (fassung?.nicht_zugeordnet?.length ?? 0)
}

/**
 * Fächer der Curricula-Seite nach Filter: `alle` (eigene immer, andere nur mit Curricula),
 * `eigene`, oder ein bestimmtes Fach (`fachId`, auch ohne Curricula). Eigene zuerst, sonst
 * alphabetisch.
 */
export function faecherFiltern(faecher, { eigene = [], filter = 'alle', fachId = null, anzahl = {} } = {}) {
  const istEigen = (f) => eigene.includes(f.id)
  return [...(faecher ?? [])]
    .filter((f) => {
      if (fachId != null) return f.id === fachId
      if (filter === 'eigene') return istEigen(f)
      return istEigen(f) || (anzahl[f.id] ?? 0) > 0
    })
    .sort((a, b) => (istEigen(b) - istEigen(a)) || a.name.localeCompare(b.name, 'de'))
}

/**
 * Texte der Abdeckungsseite: IK über das Band (`a.ik`) oder PK über die Fassung (`a.pk`).
 * `gut` ist der Zustand, den „nur Lücken“ ausblendet; `traeger` nennt je Kompetenz die Curricula.
 */
export function abdeckungTexte(a) {
  if (a?.ik) {
    const ik = a.ik
    return {
      titel: 'IK-Abdeckung im Band',
      teil: ik,
      gut: 'verknuepft',
      bilanz: `${ik.verknuepft} von ${ik.gesamt} IK verknüpft`
        + (ik.partiell ? ` · ${ik.partiell} partiell` : '') + (ik.fehlt ? ` · ${ik.fehlt} fehlen` : ''),
      traeger: (k) => k.curricula.map((c) => c.title + (c.partiell ? ' (partiell)' : '')).join(', '),
      leer: ik.gesamt ? 'Alle Kompetenzen des Bands sind verknüpft.' : 'Für dieses Band sind keine Kompetenzen hinterlegt.',
    }
  }
  const pk = a?.pk ?? { gesamt: 0, gefoerdert: 0, fehlt: 0, gruppen: [] }
  return {
    titel: 'PK-Abdeckung der Fassung',
    teil: pk,
    gut: 'gefoerdert',
    bilanz: `${pk.gefoerdert} von ${pk.gesamt} PK gefördert` + (pk.fehlt ? ` · ${pk.fehlt} ohne Lernsequenz` : ''),
    traeger: (k) => k.curricula.map((c) => `${c.title} (${c.anzahl} ${c.anzahl === 1 ? 'Lernsequenz' : 'Lernsequenzen'})`).join(', '),
    leer: pk.gesamt ? 'Alle prozessbezogenen Kompetenzen werden gefördert.' : 'Für diese Fassung sind keine prozessbezogenen Kompetenzen hinterlegt.',
  }
}
