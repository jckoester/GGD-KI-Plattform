import { describe, expect, it } from 'vitest'
import {
  ARTEN, GEGENART, ausFormular, curriculaZurAuswahl, faecherZurAuswahl, formular, formularFehler,
  fachToenung, gegenabsprache, uebernehmen, zielText,
} from './absprachen.js'

describe('Formular (0.63, AY Teil 2)', () => {
  it('vorbelegt aus einer Fundstelle: zeitlich, sonst abgestimmt', () => {
    expect(formular({ fach_code: 'PH', kapitel_id: 'k1', kapitel_titel: 'Dichte' }).art).toBe('vorher')
    expect(formular().art).toBe('abgestimmt')
  })
  it('Fehler wie im Backend', () => {
    const f = formular({ fach_code: 'PH', kapitel_id: 'k1', kapitel_titel: 'Dichte' })
    expect(formularFehler(f)).toBe('')
    expect(formularFehler({ ...f, fach_code: '' })).toContain('Fach')
    expect(formularFehler(f, { eigenesFach: 'PH' })).toContain('anderen Fach')
    expect(formularFehler({ ...f, kapitel_id: '', kapitel_titel: '' })).toContain('Kapitel')
    expect(formularFehler({ ...f, art: 'abgestimmt', text: ' ' })).toContain('abgestimmt')
    expect(formularFehler({ ...f, text: 'x'.repeat(1001) })).toContain('zu lang')
    expect(formularFehler(f, { vorhandene: [ausFormular(f)] })).toContain('schon da')
    // Die eigene beim Bearbeiten zählt nicht als doppelt
    expect(formularFehler({ ...f, id: 'a1' }, { vorhandene: [{ ...ausFormular(f), id: 'a1' }] })).toBe('')
  })
  it('ausFormular und uebernehmen', () => {
    const e = ausFormular(formular({ fach_code: 'PH', text: ' Einheiten gleich ' }))
    expect(e).toEqual({ fach_code: 'PH', kapitel_id: null, kapitel_titel: null, art: 'abgestimmt', text: 'Einheiten gleich' })
    const liste = uebernehmen([], { ...e, id: 'a1' })
    expect(uebernehmen(liste, { ...e, id: 'a1', text: 'neu' })).toEqual([{ ...e, id: 'a1', text: 'neu' }])
    expect(uebernehmen(liste, e)).toHaveLength(2)
  })
  it('Gegenabsprache: Quelle wird Ziel, Gegenart', () => {
    const g = gegenabsprache({ fach_code: 'M', art: 'vorher', art_hier: 'nachher', text: 't',
      quelle: { curriculum_id: 'c', kapitel_id: 'k', kapitel: 'Brüche' } })
    expect([g.fach_code, g.kapitel_id, g.kapitel_titel, g.art, g.id]).toEqual(['M', 'k', 'Brüche', 'nachher', null])
    expect(ARTEN.every((a) => GEGENART[GEGENART[a]] === a)).toBe(true)
  })
})

describe('Auswahl und Anzeige', () => {
  it('Fächer ohne das eigene und ohne Kürzel', () => {
    const f = faecherZurAuswahl([{ id: 1, name: 'Physik', fach_code: 'PH' }, { id: 2, name: 'Mathematik', fach_code: 'M' },
      { id: 3, name: 'Sport', fach_code: null }], 2)
    expect(f.map((s) => s.fach_code)).toEqual(['PH'])
  })
  it('Curricula: gleiche Stufe zuerst, Entwurf gekennzeichnet', () => {
    const c = curriculaZurAuswahl([
      { id: 'a', title: 'Physik Kl. 7/8', min_grade: 7, max_grade: 8 },
      { id: 'b', title: 'Physik Kl. 9/10', min_grade: 9, max_grade: 10, status: 'draft', metadata: { bp_version: '2016.V3' } }], 9)
    expect(c).toEqual([{ id: 'b', text: 'Physik Kl. 9/10 (2016.V3, Entwurf)' }, { id: 'a', text: 'Physik Kl. 7/8' }])
  })
  it('fachToenung', () => {
    expect(fachToenung('#aabbcc')).toBe('border-color: #aabbcc; background-color: #aabbcc1f;')
    expect(fachToenung('red')).toBe('border-color: red;')
    expect(fachToenung(null)).toBe('')
  })
  it('zielText', () => {
    const je = { PH: { name: 'Physik' } }
    expect(zielText({ fach_code: 'PH', kapitel_titel: 'Dichte' }, je)).toBe('Physik · Dichte')
    expect(zielText({ fach_code: 'PH' }, je)).toBe('Physik · ganzes Fach')
    expect(zielText({ fach_code: 'XX', fach: 'Chemie', ziel: { kapitel: 'Stoffe' } })).toBe('Chemie · Stoffe')
  })
})
