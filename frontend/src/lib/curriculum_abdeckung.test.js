import { describe, expect, it } from 'vitest'
import { abdeckungUeberschrift, gefilterteGruppen } from './curriculum_abdeckung.js'

const a = (ik, pk = { gesamt: 33, genutzt: 30 }) => ({
  ik: { gesamt: 65, verknuepft: 41, partiell: 0, fehlt: 24, fehlt_anderswo: 0, ...ik },
  pk,
})

describe('abdeckungUeberschrift', () => {
  it('nennt Verknüpfte, Fehlende und PK', () => {
    expect(abdeckungUeberschrift(a({}))).toBe('Abdeckung: 41 von 65 IK verknüpft · 24 fehlen · PK 30 von 33 gefördert')
  })
  it('nennt partielle und andere Curricula des Bands', () => {
    expect(abdeckungUeberschrift(a({ partiell: 2, fehlt_anderswo: 3 }))).toBe(
      'Abdeckung: 41 von 65 IK verknüpft · 2 partiell · 24 fehlen (3 davon in anderen Curricula des Bands) · PK 30 von 33 gefördert',
    )
  })
  it('ohne Kompetenzen und ohne Daten', () => {
    expect(abdeckungUeberschrift(a({ gesamt: 0 }))).toBe('Abdeckung: keine Kompetenzen des Bands gefunden')
    expect(abdeckungUeberschrift(null)).toBe('Abdeckung')
  })
})

describe('gefilterteGruppen', () => {
  const gruppen = [
    { titel: 'Zahl', kompetenzen: [{ zustand: 'verknuepft' }, { zustand: 'fehlt' }] },
    { titel: 'Raum', kompetenzen: [{ zustand: 'verknuepft' }] },
  ]
  it('zeigt nur Lücken und lässt leere Gruppen weg', () => {
    expect(gefilterteGruppen(gruppen, true)).toEqual([{ titel: 'Zahl', kompetenzen: [{ zustand: 'fehlt' }] }])
  })
  it('zeigt alles', () => {
    expect(gefilterteGruppen(gruppen, false)).toHaveLength(2)
  })
})
