import { describe, it, expect } from 'vitest'
import { lernsequenzStd, kapitelStd, curriculumStd } from './curriculum.js'

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
