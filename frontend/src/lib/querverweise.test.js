import { describe, expect, it } from 'vitest'
import {
    bezugText,
    fachKuerzel,
    faecher,
    fehlendeIds,
    kompetenzIdsImCurriculum,
    kompetenzIdsImFachplan,
    kuenftigText,
    stufenText,
    uebernehmen,
    zeilenText,
} from './querverweise.js'

const ph = (extra = {}) => ({
    ziel_id: 'p1', typ: 'ik', fach_id: 2, fach: 'Physik', fach_code: 'PH', icon: 'atom',
    color: '#2563eb', nr: '3.2.1(3)', titel: 'Masse und Volumen', min_grade: 7, max_grade: 8,
    status: 'active', ab_schuljahr: null, ...extra,
})

describe('fachKuerzel', () => {
    it('nimmt den Bildungsplan-Code', () => expect(fachKuerzel(ph())).toBe('PH'))
    it('fällt ohne Code auf den Namen zurück (Deutsch)', () =>
        expect(fachKuerzel({ fach: 'Deutsch', fach_code: null })).toBe('Deu'))
})

describe('faecher', () => {
    it('fasst je Fach zusammen und zählt, in der Reihenfolge der Liste', () => {
        const liste = [ph(), ph({ ziel_id: 'p2' }), { ...ph(), fach_id: 3, fach: 'Chemie', fach_code: 'CH' }]
        expect(faecher(liste).map((f) => [f.kuerzel, f.anzahl])).toEqual([['PH', 2], ['CH', 1]])
    })
    it('leer bleibt leer', () => expect(faecher(undefined)).toEqual([]))
})

describe('stufenText', () => {
    it('Spanne', () => expect(stufenText(ph())).toBe('Kl. 7/8'))
    it('eine Stufe', () => expect(stufenText({ min_grade: 9, max_grade: 9 })).toBe('Kl. 9'))
    it('ohne Stufen', () => expect(stufenText({ min_grade: null, max_grade: null })).toBe(''))
})

describe('kuenftigText', () => {
    it('aktiv: nichts', () => expect(kuenftigText(ph())).toBe(''))
    it('mit Jahr', () => expect(kuenftigText(ph({ status: 'upcoming', ab_schuljahr: 2027 }))).toBe('ab 2027/28'))
    it('Jahrhundertwechsel zweistellig', () =>
        expect(kuenftigText(ph({ status: 'upcoming', ab_schuljahr: 2099 }))).toBe('ab 2099/00'))
    it('ohne Jahr', () => expect(kuenftigText(ph({ status: 'upcoming' }))).toBe('künftige Fassung'))
})

describe('zeilenText', () => {
    it('Kompetenz', () => expect(zeilenText(ph())).toBe('Kl. 7/8 · 3.2.1(3) Masse und Volumen'))
    it('Bereich gekennzeichnet, ohne Stufen', () =>
        expect(zeilenText(ph({ typ: 'bereich', nr: '3.4.3', titel: 'Schwingungen', min_grade: null, max_grade: null })))
            .toBe('Bereich 3.4.3 Schwingungen'))
})

describe('bezugText', () => {
    it('nennt die Fächer, mehrfache mit Zahl', () => {
        const liste = [ph(), ph({ ziel_id: 'p2' }), { ...ph(), fach_id: 3, fach: 'Chemie' }]
        expect(bezugText(liste)).toBe('Bezug zu Physik (2), Chemie')
    })
    it('leer', () => expect(bezugText([])).toBe(''))
})

describe('kompetenzIdsImCurriculum', () => {
    it('sammelt die IDs der IK-Spalte, ohne Doppel und ohne Altformat', () => {
        const curriculum = { kapitel: [{ lernsequenzen: [
            { metadata: { eintraege: [
                { ik: [{ node_id: 'a', nr: '1' }, { node_id: null, nr: '2' }] },
                { ik: '3.1.1, 3.1.2' },
                { ik: [{ node_id: 'a' }, { node_id: 'b' }] },
            ] } },
            { metadata: {} },
        ] }, {}] }
        expect(kompetenzIdsImCurriculum(curriculum)).toEqual(['a', 'b'])
    })
    it('ohne Curriculum', () => expect(kompetenzIdsImCurriculum(null)).toEqual([]))
})

describe('Zwischenspeicher', () => {
    it('fragt nur Neues und merkt sich auch Leeres', () => {
        let speicher = new Map()
        expect(fehlendeIds(['a', 'b'], speicher)).toEqual(['a', 'b'])
        speicher = uebernehmen(speicher, ['a', 'b'], { a: [ph()] })
        expect(speicher.get('a')).toHaveLength(1)
        expect(speicher.get('b')).toEqual([])
        expect(fehlendeIds(['a', 'b', 'c'], speicher)).toEqual(['c'])
    })
})

describe('kompetenzIdsImFachplan', () => {
    it('geht rekursiv durch die Bereiche', () => {
        const plan = { leitideen: [
            { ik_kompetenzen: [{ id: 'a' }], unter_leitideen: [{ ik_kompetenzen: [{ id: 'b' }, { id: 'a' }] }] },
            { ik_kompetenzen: [] },
        ] }
        expect(kompetenzIdsImFachplan(plan)).toEqual(['a', 'b'])
    })
    it('ohne Plan', () => expect(kompetenzIdsImFachplan(null)).toEqual([]))
})
