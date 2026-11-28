import { describe, expect, it } from 'vitest'
import { kurz, ohneBezug, satz, staerke, tabelle } from './vernetzung_matrix.js'
import { vernetzungPfad } from './zeitachse.js'

const M = { id: 1, code: 'M', name: 'Mathematik' }
const PH = { id: 2, code: 'PH', name: 'Physik' }
const BIO = { id: 3, code: 'BIO', name: 'Biologie' }
const z = (a, b, x = {}) => ({ a, b, absprachen: 0, verletzt: 0, kompetenz: 0, bereich: 0, ganzes_fach: 0, ...x })
const daten = {
  stufe: 8, faecher: [M, PH, BIO],
  zellen: [z(1, 1, { kompetenz: 40 }), z(1, 2, { absprachen: 2, verletzt: 1, kompetenz: 3 }), z(2, 3, { bereich: 5, ganzes_fach: 1 })],
}

describe('Matrix der Vernetzung (Teil B)', () => {
  it('zählt nach Schaltern', () => {
    const zelle = daten.zellen[1]
    expect(staerke(zelle)).toBe(5)
    expect(staerke(zelle, { querverweise: false })).toBe(2)
    expect(staerke(daten.zellen[2])).toBe(1)
    expect(staerke(daten.zellen[2], { bereiche: true })).toBe(6)
    expect(staerke(undefined)).toBe(0)
  })
  it('ist symmetrisch, die Diagonale bleibt ohne Farbe und zählt nicht zum Höchstwert', () => {
    const t = tabelle(daten)
    expect(t.max).toBe(5)
    const [m, ph] = t.zeilen
    expect(m.zellen[1].n).toBe(5)
    expect(ph.zellen[0].n).toBe(5)            // dieselbe Zelle von der anderen Seite
    expect(m.zellen[0]).toMatchObject({ diagonal: true, n: 40, farbe: 0 })
    expect(m.zellen[1].farbe).toBe(5)
    expect(m.zellen[2]).toMatchObject({ n: 0, farbe: 0 })
    expect(m.summe).toBe(5)
    expect(ohneBezug(tabelle({ faecher: [M], zellen: [z(1, 1, { kompetenz: 3 })] }))).toBe(true)
  })
  it('beschriftet kurz und als Satz', () => {
    const zelle = daten.zellen[1]
    expect(kurz(zelle)).toBe('A 2 · Q 3')
    expect(kurz(daten.zellen[2], { bereiche: true })).toBe('A 1 · B 5')
    expect(satz(M, PH, zelle)).toBe('Mathematik und Physik: 2 Absprachen (1 nicht eingehalten), 3 Querverweise')
    expect(satz(PH, BIO, daten.zellen[2])).toBe('Physik und Biologie: 1 Absprache mit dem ganzen Fach')
    expect(satz(M, M, daten.zellen[0])).toBe('Mathematik, im eigenen Fach: 40 Querverweise')
    expect(satz(M, BIO, undefined)).toBe('Mathematik und Biologie: keine Bezüge')
  })
  it('Zelle führt in die Zeitachse mit Zeilenfach, Stufe und Spaltenfach als Spur', () => {
    expect(vernetzungPfad({ fach: 'M', stufe: 8, spur: 2, schuljahr: '2027/28', aktuelles: '2026/27' }))
      .toBe('/knowledge/connections?fach=M&spur=2&schuljahr=2027%2F28&stufe=8')
  })
})
