import { describe, it, expect } from 'vitest'
import { kurzdatum, termine, terminzeile } from './ab_wochen.js'

// Montage 08.06., 22.06., 06.07. = A-Wochen; 15.06., 29.06. = B-Wochen.
// Dazu je ein Dienstag, damit der Wochentagsfilter etwas zu tun hat.
const KALENDER = {
  halbjahr: 2,
  a_woche: ['2026-06-08', '2026-06-09', '2026-06-22', '2026-07-06'],
  b_woche: ['2026-06-15', '2026-06-16', '2026-06-29'],
}

describe('kurzdatum', () => {
  it('formatiert ISO zu Tag.Monat', () => {
    expect(kurzdatum('2026-06-08')).toBe('08.06.')
  })

  it('rechnet nicht über Date — sonst verschöbe die Zeitzone den Tag', () => {
    // `new Date('2026-01-01')` ist UTC-Mitternacht und in westlichen Zonen der 31.12.
    expect(kurzdatum('2026-01-01')).toBe('01.01.')
  })
})

describe('termine', () => {
  it('filtert nach Wochentag', () => {
    expect(termine(KALENDER, 0, 'a_woche').daten).toEqual(['08.06.', '22.06.', '06.07.'])
    expect(termine(KALENDER, 1, 'a_woche').daten).toEqual(['09.06.'])
  })

  it('trennt A- und B-Woche', () => {
    expect(termine(KALENDER, 0, 'b_woche').daten).toEqual(['15.06.', '29.06.'])
  })

  it('zeigt für wöchentliche Muster nichts an', () => {
    // Dort ist die Frage „in welcher Woche?" gegenstandslos — jede Woche.
    expect(termine(KALENDER, 0, 'woechentlich')).toEqual({ daten: [], gesamt: 0 })
  })

  it('bleibt leer, solange der Kalender fehlt', () => {
    expect(termine(null, 0, 'a_woche')).toEqual({ daten: [], gesamt: 0 })
  })

  it('begrenzt die Anzahl, meldet aber die Gesamtzahl', () => {
    const { daten, gesamt } = termine(KALENDER, 0, 'a_woche', { anzahl: 2 })
    expect(daten).toEqual(['08.06.', '22.06.'])
    expect(gesamt).toBe(3)
  })

  it('übergeht Termine vor dem Stichtag', () => {
    expect(termine(KALENDER, 0, 'a_woche', { ab: '2026-06-22' }).daten).toEqual([
      '22.06.',
      '06.07.',
    ])
  })
})

describe('terminzeile', () => {
  it('hängt Auslassungspunkte an, wenn mehr folgen', () => {
    expect(terminzeile(KALENDER, 0, 'a_woche', { anzahl: 2 })).toBe('08.06. · 22.06. · …')
  })

  it('lässt sie weg, wenn alles gezeigt wird', () => {
    expect(terminzeile(KALENDER, 0, 'b_woche')).toBe('15.06. · 29.06.')
  })

  it('ist leer, wenn es nichts zu zeigen gibt', () => {
    expect(terminzeile(KALENDER, 0, 'woechentlich')).toBe('')
  })
})
