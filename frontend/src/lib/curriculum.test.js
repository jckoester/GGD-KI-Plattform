import { describe, it, expect } from 'vitest'
import { lernsequenzStd, kapitelStd, curriculumStd, ersetztHinweis, toteVerweiseBeschriftungen, entwurfHinweis, ENTWURF_HINWEIS, ENTWURF_NUR_LESEN } from './curriculum.js'

describe('lernsequenzStd', () => {
    it('liest eine Zahl', () => {
        expect(lernsequenzStd({ metadata: { std: 5 } })).toBe(5)
    })
    it('parst einen String', () => {
        expect(lernsequenzStd({ metadata: { std: '3' } })).toBe(3)
    })
    it('fehlende/leere/ungültige Werte → 0', () => {
        expect(lernsequenzStd({ metadata: {} })).toBe(0)
        expect(lernsequenzStd({ metadata: { std: '' } })).toBe(0)
        expect(lernsequenzStd({ metadata: { std: 'abc' } })).toBe(0)
        expect(lernsequenzStd(undefined)).toBe(0)
        expect(lernsequenzStd(null)).toBe(0)
    })
})

describe('kapitelStd', () => {
    it('summiert die Lernsequenz-Stunden', () => {
        const kap = {
            lernsequenzen: [
                { metadata: { std: 2 } },
                { metadata: { std: '3' } },
                { metadata: {} },
            ],
        }
        expect(kapitelStd(kap)).toBe(5)
    })
    it('leeres/fehlendes Kapitel → 0', () => {
        expect(kapitelStd({})).toBe(0)
        expect(kapitelStd({ lernsequenzen: [] })).toBe(0)
        expect(kapitelStd(undefined)).toBe(0)
    })
})

describe('curriculumStd', () => {
    it('summiert über alle Kapitel und Lernsequenzen', () => {
        const curr = {
            kapitel: [
                { lernsequenzen: [{ metadata: { std: 4 } }, { metadata: { std: 6 } }] },
                { lernsequenzen: [{ metadata: { std: 10 } }] },
            ],
        }
        expect(curriculumStd(curr)).toBe(20)
    })
    it('leeres/null Curriculum → 0', () => {
        expect(curriculumStd({ kapitel: [] })).toBe(0)
        expect(curriculumStd(null)).toBe(0)
    })
})


describe('toteVerweiseBeschriftungen (0.45)', () => {
  const tot = '14b8e715-b655-487c-bcdd-f4c81ea9c02a'
  const spalte = '4289d004-9362-4758-8184-2a84a1660b41'
  const curr = { kapitel: [{ lernsequenzen: [{ metadata: { eintraege: [
    { hinweise: `Siehe #[PH 3.4.3](ik:${tot}) und mehr`, ik: [{ node_id: spalte, nr: '3.1(2)' }] },
  ] } }] }] }
  it('nimmt die Beschriftung aus dem Hinweis, sonst die Nummer, sonst die Kennung', () => {
    expect(toteVerweiseBeschriftungen(curr, [tot, spalte, 'x'])).toEqual(['PH 3.4.3', '3.1(2)', 'x'])
    expect(toteVerweiseBeschriftungen(curr, [])).toEqual([])
  })
})

describe('ersetztHinweis (0.45)', () => {
  it('eine und mehrere Einheiten', () => {
    expect(ersetztHinweis([])).toBe('')
    expect(ersetztHinweis(['Trigonometrie'])).toMatch(/^Die Einheit „Trigonometrie“ hängt an einem Kapitel/)
    expect(ersetztHinweis(['A', 'B'])).toMatch(/^2 Einheiten \(„A“, „B“\) hängen/)
  })
})

describe('entwurfHinweis (0.52, AZ)', () => {
  it('Fachschaft: der Satz, dass alle Lehrkräfte mitlesen', () => {
    expect(entwurfHinweis({ status: 'draft', can_edit: true })).toBe(ENTWURF_HINWEIS)
    expect(ENTWURF_HINWEIS).toContain('Alle Lehrkräfte können ihn lesen')
  })
  it('wer nur liest: „nur lesen“ und wer bearbeitet', () => {
    expect(entwurfHinweis({ status: 'draft', can_edit: false })).toBe(ENTWURF_NUR_LESEN)
    expect(ENTWURF_NUR_LESEN).toMatch(/^Entwurf — nur lesen\./)
    expect(ENTWURF_NUR_LESEN).toContain('Fachschaft')
  })
  it('veröffentlicht oder ohne Curriculum: kein Hinweis', () => {
    expect(entwurfHinweis({ status: 'active', can_edit: false })).toBe('')
    expect(entwurfHinweis(null)).toBe('')
  })
})
