import { describe, it, expect } from 'vitest'
import { editionLoadPlan } from './editions.js'

describe('editionLoadPlan', () => {
    it('ohne Fach wird nicht geladen', () => {
        expect(editionLoadPlan({ subjectId: null, grade: 9 })).toEqual({
            load: false,
            bpFilter: null,
        })
    })

    it('explizite Edition gilt sofort — ohne Warten', () => {
        // Der Fall des Curriculum-Editors: Das Curriculum kennt seine Edition
        // (metadata.bp_version), es gibt nichts aufzulösen.
        expect(
            editionLoadPlan({ subjectId: 3, bpVersion: '2016.V2', grade: 9 }),
        ).toEqual({ load: true, bpFilter: '2016.V2' })
    })

    it('explizite Edition schlägt eine bereits aufgelöste', () => {
        expect(
            editionLoadPlan({
                subjectId: 3,
                bpVersion: '2016',
                grade: 9,
                resolved: '2016.V2',
            }),
        ).toEqual({ load: true, bpFilter: '2016' })
    })

    it('ohne Stufe gibt es nichts aufzulösen → ungefiltert laden', () => {
        expect(editionLoadPlan({ subjectId: 3 })).toEqual({
            load: true,
            bpFilter: null,
        })
    })

    it('laufende Auflösung: NICHT laden', () => {
        // Der eigentliche Fehler: Hier wurde bisher ungefiltert geladen und
        // gleich darauf gefiltert nachgeladen. Welche Antwort zuletzt eintraf,
        // entschied über doppelte Einträge in der Liste.
        expect(
            editionLoadPlan({ subjectId: 3, grade: 9, resolved: undefined }),
        ).toEqual({ load: false, bpFilter: null })
    })

    it('abgeschlossene Auflösung: mit Edition laden', () => {
        expect(
            editionLoadPlan({ subjectId: 3, grade: 9, resolved: '2016.V2' }),
        ).toEqual({ load: true, bpFilter: '2016.V2' })
    })

    it('Auflösung ergab „keine versionierten Knoten" → ungefiltert laden', () => {
        // null ist ein Ergebnis, kein ausstehender Zustand: Das Fach hat keine
        // Editionen, also darf ohne Filter geladen werden.
        expect(
            editionLoadPlan({ subjectId: 3, grade: 9, resolved: null }),
        ).toEqual({ load: true, bpFilter: null })
    })

    it('unterscheidet ausstehend (undefined) von ergebnislos (null)', () => {
        const ausstehend = editionLoadPlan({ subjectId: 3, grade: 9 })
        const ergebnislos = editionLoadPlan({ subjectId: 3, grade: 9, resolved: null })
        expect(ausstehend.load).toBe(false)
        expect(ergebnislos.load).toBe(true)
    })

    it('leerer Aufruf stürzt nicht ab', () => {
        expect(editionLoadPlan()).toEqual({ load: false, bpFilter: null })
    })
})
