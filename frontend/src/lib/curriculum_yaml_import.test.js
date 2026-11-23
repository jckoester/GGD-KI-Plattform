import { describe, expect, it } from 'vitest'
import { MAX_ZEICHEN, dateiLesen, ersetzbar, kannAnlegen, summenText, vorauswahl } from './curriculum_yaml_import.js'

const v = (vorhanden, extra = {}) => ({ ok: true, fehler: [], vorhanden, ...extra })

describe('Ersatz vorauswählen (F2)', () => {
  it('genau ein ersetzbares Curriculum ist vorausgewählt', () => {
    expect(vorauswahl(v([{ id: 'a', offener_entwurf: null }]))).toBe('a')
  })
  it('mit offenem Entwurf nicht ersetzbar, dann neuer Entwurf', () => {
    const vs = v([{ id: 'a', offener_entwurf: 'e' }])
    expect(ersetzbar(vs)).toEqual([])
    expect(vorauswahl(vs)).toBeNull()
  })
  it('bei mehreren wählt die Lehrkraft selbst', () => {
    expect(vorauswahl(v([{ id: 'a', offener_entwurf: null }, { id: 'b', offener_entwurf: null }]))).toBeNull()
  })
  it('ohne Vorschau nichts', () => {
    expect(vorauswahl(null)).toBeNull()
  })
})

describe('Anlegen', () => {
  it('nur nach einer fehlerfreien Vorschau zum aktuellen Text', () => {
    expect(kannAnlegen(v([]))).toBe(true)
    expect(kannAnlegen(v([]), { geaendert: true })).toBe(false)
    expect(kannAnlegen({ ok: false, fehler: ['x'] })).toBe(false)
    expect(kannAnlegen(null)).toBe(false)
  })
})

describe('Summen', () => {
  it('mit und ohne Stunden, Einzahl', () => {
    expect(summenText({ kapitel: 2, lernsequenzen: 1, eintraege: 1, stunden: 0 }))
      .toBe('2 Kapitel · 1 Lernsequenz · 1 Eintrag')
    expect(summenText({ kapitel: 1, lernsequenzen: 3, eintraege: 9, stunden: 12.5 }))
      .toBe('1 Kapitel · 3 Lernsequenzen · 9 Einträge · 12,5 Stunden')
  })
})

describe('Datei lesen', () => {
  it('liest Text und weist zu große Dateien ab', async () => {
    expect(await dateiLesen(new Blob(['a: 1']))).toEqual({ text: 'a: 1', fehler: null })
    expect((await dateiLesen(new Blob(['x'.repeat(MAX_ZEICHEN + 1)]))).fehler).toMatch(/zu groß/)
    expect(await dateiLesen(null)).toEqual({ text: '', fehler: null })
  })
})
