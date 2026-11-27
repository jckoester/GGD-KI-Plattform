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

describe('Lesesicht (Schritt 4)', () => {
  it('Pfade und Texte', async () => {
    const { kapitelPfad, ortText, gegenabspracheHref, findeVonAussen, hatAbsprachen } = await import('./absprachen.js')
    const ort = { curriculum_id: 'c', kapitel_id: 'k', kapitel: 'Dichte', curriculum: 'Physik Kl. 8', status: 'draft' }
    expect(kapitelPfad(ort)).toBe('/knowledge/curriculum/c#kapitel-k')
    expect(kapitelPfad(null)).toBeNull()
    expect(ortText(ort)).toBe('Dichte · Physik Kl. 8 (Entwurf)')
    expect(ortText(null, 'Dichte')).toBe('Dichte')
    expect(ortText(null)).toBe('ganzes Fach')
    expect(gegenabspracheHref('c1', { id: 'a b' })).toBe('/knowledge/curriculum/c1/edit?gegen=a%20b')
    const daten = { kapitel: { k1: { eigene: [], von_aussen: [{ id: 'x' }] } } }
    expect(findeVonAussen(daten, 'x')).toEqual({ kapId: 'k1', absprache: { id: 'x' } })
    expect(findeVonAussen(daten, 'y')).toBeNull()
    expect(hatAbsprachen([], [])).toBe(false)
    expect(hatAbsprachen([], [{}])).toBe(true)
  })
})

describe('pruefungText (Teil B)', () => {
  it('eingehalten, verletzt, offen', async () => {
    const { pruefungText } = await import('./absprachen.js')
    expect(pruefungText({ ergebnis: 'eingehalten', hier: 'Kl. 8, KW 44', dort: 'Kl. 8, KW 38–40' }))
      .toBe('Passt zu den Jahresverlaufsplänen (hier Kl. 8, KW 44, dort Kl. 8, KW 38–40).')
    expect(pruefungText({ ergebnis: 'verletzt', hier: 'Kl. 8', dort: 'Kl. 9' }))
      .toBe('Laut Jahresverlaufsplänen nicht eingehalten (hier Kl. 8, dort Kl. 9).')
    expect(pruefungText({ ergebnis: 'offen', grund: 'ohne_wochen' })).toBe('')
    expect(pruefungText(null)).toBe('')
  })
})

describe('absprachenJeAbschnitt (Teil B)', () => {
  it('jedes Kapitel nur am ersten Abschnitt, auch sequenzgenau', async () => {
    const { absprachenJeAbschnitt } = await import('./absprachen.js')
    const daten = { k1: { eigene: [{ id: 'a' }], von_aussen: [{ id: 'b' }] }, k2: { eigene: [], von_aussen: [{ id: 'c' }] } }
    const r = absprachenJeAbschnitt([{ kapitel_ids: ['k1'] }, { kapitel_ids: ['k1', 'k2'] }, { kapitel_ids: [] }], daten)
    expect(r.map((x) => [x.eigene.map((a) => a.id), x.vonAussen.map((a) => a.id)])).toEqual([[['a'], ['b']], [[], ['c']], [[], []]])
    const s = absprachenJeAbschnitt([{ sequenz_ids: ['s1', 's2'] }, { sequenz_ids: ['s3'] }], daten,
      { planungsart: 'sequenz', kapitelVon: { s1: 'k1', s2: 'k1', s3: 'k2' } })
    expect(s.map((x) => x.eigene.length + x.vonAussen.length)).toEqual([2, 1])
  })
})

describe('einheitAbsprachen (Teil B)', () => {
  it('Fächer und verletzt', async () => {
    const { einheitAbsprachen } = await import('./absprachen.js')
    expect(einheitAbsprachen(null)).toBeNull()
    expect(einheitAbsprachen({ eigene: [], von_aussen: [] })).toBeNull()
    const k = { eigene: [{ fach: 'Physik', pruefung: { ergebnis: 'eingehalten' } }],
      von_aussen: [{ fach: 'Chemie', pruefung: { ergebnis: 'verletzt' } }, { fach: 'Physik', beidseitig: true }] }
    expect(einheitAbsprachen(k)).toEqual({ text: 'Absprachen mit Physik, Chemie', verletzt: true })
  })
})
