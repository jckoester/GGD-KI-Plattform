import { describe, expect, it } from 'vitest'
import { anlegenText, anzulegen, artText, dateienLesen, ergebnisText, MAX_DATEIEN } from './curriculum_vorlagen.js'

const datei = (name, text = 'fach_code: PH') => ({ name, size: text.length, text: async () => text })

describe('dateienLesen (0.62, BH)', () => {
  it('liest und sortiert nach Namen, Zahlen natürlich', async () => {
    const { dateien, fehler } = await dateienLesen([datei('ph10.yaml'), datei('ph7.yaml')])
    expect(dateien.map((d) => d.name)).toEqual(['ph7.yaml', 'ph10.yaml'])
    expect(dateien[0].yaml).toBe('fach_code: PH')
    expect(fehler).toEqual([])
  })
  it('höchstens 60 Dateien, der Rest mit Fehler', async () => {
    const viele = Array.from({ length: MAX_DATEIEN + 2 }, (_, i) => datei(`${i}.yaml`))
    const { dateien, fehler } = await dateienLesen(viele)
    expect(dateien).toHaveLength(MAX_DATEIEN)
    expect(fehler).toHaveLength(2)
    expect(fehler[0].fehler).toContain('Höchstens 60')
  })
  it('zu große Einzeldatei', async () => {
    const { dateien, fehler } = await dateienLesen([datei('gross.yaml', 'x'.repeat(200_001))])
    expect(dateien).toEqual([])
    expect(fehler[0].name).toBe('gross.yaml')
  })
})

describe('Texte', () => {
  it('artText', () => {
    expect(artText({ ok: true, art: 'neu' })).toBe('neuer Entwurf')
    expect(artText({ ok: true, art: 'ersetzt', ersetzt_titel: 'Physik Kl. 7/8' })).toContain('„Physik Kl. 7/8“')
    expect(artText({ ok: true, art: 'zusaetzlich' })).toContain('Datum')
    expect(artText({ ok: false })).toBe('wird nicht angelegt')
  })
  it('anlegenText und ergebnisText', () => {
    expect(anlegenText({ ok: 0 })).toBe('')
    expect(anlegenText({ ok: 1 })).toBe('1 Entwurf anlegen')
    expect(anlegenText({ ok: 4 })).toBe('4 Entwürfe anlegen')
    expect(ergebnisText({ ok: 3, fehler: 0 })).toBe('3 Entwürfe angelegt.')
    expect(ergebnisText({ ok: 1, fehler: 1 })).toBe('1 Entwurf angelegt, 1 Datei mit Fehlern.')
  })
  it('anzulegen: nur fehlerfreie, Reihenfolge bleibt', () => {
    const dateien = [{ name: 'a' }, { name: 'b' }, { name: 'c' }]
    const vorschau = { dateien: [{ datei: 'a', ok: true }, { datei: 'b', ok: false }, { datei: 'c', ok: true }] }
    expect(anzulegen(dateien, vorschau).map((d) => d.name)).toEqual(['a', 'c'])
  })
})
