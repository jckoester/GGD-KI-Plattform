/**
 * Vernetzung der Fächer, Teil B (0.67, F10): die Übersicht Fach × Fach einer Klassenstufe.
 *
 * Rein, ohne Oberfläche. Die Antwort von `GET /context/vernetzung/matrix` trägt je Fächerpaar
 * eine Zelle (a < b); die Tabelle ist symmetrisch, damit jede Zeile vollständig zu lesen ist.
 * Die Färbung nutzt die Mengenstufen der Leitlinien-Übersicht (`heatmap_stufen.js`,
 * `--diagramm-stufe-1…5`), mit `validate_palette.js --ordinal` auch gegen `bg` geprüft. Die
 * Diagonale (eigenes Fach) bleibt ohne Farbe, sonst überstrahlt sie die Paare.
 */
import { stufe } from './heatmap_stufen.js'

const LEER = { absprachen: 0, verletzt: 0, kompetenz: 0, bereich: 0, ganzes_fach: 0 }

/** Wie viele Bezüge eine Zelle unter den Schaltern zählt. */
export function staerke(z, { querverweise = true, bereiche = false } = {}) {
  if (!z) return 0
  const qv = querverweise ? z.kompetenz + (bereiche ? z.bereich : 0) : 0
  return z.absprachen + z.ganzes_fach + qv
}

/** Kurzform für die Zelle: „A 2 · Q 5“ (leere Teile fallen weg). */
export function kurz(z, { querverweise = true, bereiche = false } = {}) {
  if (!z) return ''
  const teile = []
  if (z.absprachen + z.ganzes_fach) teile.push(`A ${z.absprachen + z.ganzes_fach}`)
  if (querverweise && z.kompetenz) teile.push(`Q ${z.kompetenz}`)
  if (querverweise && bereiche && z.bereich) teile.push(`B ${z.bereich}`)
  return teile.join(' · ')
}

/** Der ganze Satz für Tooltip und Bildschirmleser. */
export function satz(zeile, spalte, z, { querverweise = true, bereiche = false } = {}) {
  const diagonal = zeile.id === spalte.id
  const wer = diagonal ? `${zeile.name}, im eigenen Fach` : `${zeile.name} und ${spalte.name}`
  if (!staerke(z, { querverweise, bereiche })) return `${wer}: keine Bezüge`
  const teile = []
  if (z.absprachen) {
    teile.push(`${z.absprachen} ${z.absprachen === 1 ? 'Absprache' : 'Absprachen'}`
      + (z.verletzt ? ` (${z.verletzt} nicht eingehalten)` : ''))
  }
  if (z.ganzes_fach) teile.push(`${z.ganzes_fach} ${z.ganzes_fach === 1 ? 'Absprache' : 'Absprachen'} mit dem ganzen Fach`)
  if (querverweise && z.kompetenz) teile.push(`${z.kompetenz} ${z.kompetenz === 1 ? 'Querverweis' : 'Querverweise'}`)
  if (querverweise && bereiche && z.bereich) teile.push(`${z.bereich} über ganze Bereiche`)
  return `${wer}: ${teile.join(', ')}`
}

/**
 * Die Tabelle: `zeilen[i].zellen[j]` mit `z` (Zählung oder Nullen), `n` (Stärke), `farbe`
 * (Stufe 0…5, die Diagonale 0) und `diagonal`. `max` ist der Höchstwert außerhalb der Diagonale.
 */
export function tabelle(daten, schalter = {}) {
  const faecher = daten?.faecher ?? []
  const je = new Map((daten?.zellen ?? []).map((z) => [`${Math.min(z.a, z.b)}-${Math.max(z.a, z.b)}`, z]))
  const finde = (a, b) => je.get(`${Math.min(a, b)}-${Math.max(a, b)}`) ?? LEER
  let max = 0
  for (const z of je.values()) if (z.a !== z.b) max = Math.max(max, staerke(z, schalter))
  const zeilen = faecher.map((f) => ({
    fach: f,
    summe: 0,
    zellen: faecher.map((g) => {
      const z = finde(f.id, g.id)
      const n = staerke(z, schalter)
      const diagonal = f.id === g.id
      return { fach: g, z, n, diagonal, farbe: diagonal ? 0 : stufe(n, max) }
    }),
  }))
  for (const r of zeilen) r.summe = r.zellen.reduce((s, c) => s + (c.diagonal ? 0 : c.n), 0)
  return { faecher, zeilen, max }
}

/** Ohne einen einzigen Bezug zwischen zwei Fächern (dann sagt die Seite es statt einer leeren Tabelle). */
export function ohneBezug(t) {
  return t.max === 0
}
