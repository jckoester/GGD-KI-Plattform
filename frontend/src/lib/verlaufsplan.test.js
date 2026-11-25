import { describe, expect, it } from 'vitest'
import {
    abschnittFarbe, bezugText, bezugsfeld, bilanzStand, dauerVorschlag, einheiten, hinweise, neuerAbschnitt, schuljahreZumAnlegen, tagText, teilen,
    umsetzen, verschieben, wochenBisZuDenFerien, wochenText, zeitraumText, zumSpeichern,
} from './verlaufsplan.js'
import { ueColorIndex } from './planner.js'

// Ferienabschnitte 2025/26, wie der Server sie liefert
const FERIEN = [
    { von_woche: 1, bis_woche: 6, endet_mit: 'Herbstferien' },
    { von_woche: 7, bis_woche: 13, endet_mit: 'Weihnachtsferien' },
    { von_woche: 31, bis_woche: 37, endet_mit: 'Schuljahresende' },
]

describe('Texte', () => {
    it('Datum und Zeitraum', () => {
        expect(tagText('2025-09-15')).toBe('15.09.')
        expect(zeitraumText({ beginn: '2025-09-15', ende: '2025-10-10' })).toBe('15.09.–10.10.')
        expect(zeitraumText({ beginn: '2025-09-15', ende: '2025-09-15' })).toBe('15.09.')
        expect(zeitraumText({ beginn: null })).toBe('')
    })
    it('Wochen', () => {
        expect(wochenText({ von_woche: 5, bis_woche: 10 })).toBe('Woche 5–10')
        expect(wochenText({ von_woche: 3, bis_woche: 3 })).toBe('Woche 3')
    })
    it('Hinweise', () => {
        expect(hinweise({ ueber_ferien: ['Herbstferien'], vor_ferien: 'Weihnachtsferien',
            halbjahreswechsel: true, lang: true, ausserhalb: 2 })).toEqual([
            'über die Herbstferien', 'endet vor den Weihnachtsferien', 'Halbjahreswechsel',
            'länger als 6 Wochen', '2 Wochen nach Schuljahresende'])
        expect(hinweise({ ausserhalb: 1 })).toEqual(['1 Woche nach Schuljahresende'])
        expect(hinweise(null)).toEqual([])
    })
})

describe('bis zu den Ferien', () => {
    it('zählt bis zum Ende des Ferienabschnitts', () => {
        expect(wochenBisZuDenFerien(1, FERIEN)).toBe(6)
        expect(wochenBisZuDenFerien(5, FERIEN)).toBe(2)
        expect(wochenBisZuDenFerien(31, FERIEN)).toBe(7)
    })
    it('ohne Kalender oder hinter dem Schuljahr: null', () => {
        expect(wochenBisZuDenFerien(40, FERIEN)).toBeNull()
        expect(wochenBisZuDenFerien(1, undefined)).toBeNull()
    })
})

describe('Reihenfolge', () => {
    const l = ['a', 'b', 'c']
    it('verschieben', () => {
        expect(verschieben(l, 1, -1)).toEqual(['b', 'a', 'c'])
        expect(verschieben(l, 1, 1)).toEqual(['a', 'c', 'b'])
        expect(verschieben(l, 0, -1)).toBe(l)
        expect(verschieben(l, 2, 1)).toBe(l)
    })
    it('umsetzen', () => {
        expect(umsetzen(l, 0, 2)).toEqual(['b', 'c', 'a'])
        expect(umsetzen(l, 2, 0)).toEqual(['c', 'a', 'b'])
        expect(umsetzen(l, 1, 1)).toBe(l)
        expect(umsetzen(l, 1, 5)).toBe(l)
    })
})

describe('Farbe', () => {
    it('nach dem ersten Kapitel, ohne Kapitel keine', () => {
        const reihe = ['k1', 'k2']
        expect(abschnittFarbe({ kapitel_ids: ['k2', 'k1'] }, reihe)).toBe(ueColorIndex(1))
        expect(abschnittFarbe({ kapitel_ids: [] }, reihe)).toBeNull()
        expect(abschnittFarbe({ kapitel_ids: ['fremd'] }, reihe)).toBeNull()
    })
    it('sequenzgenau: nach dem Kapitel der ersten Sequenz', () => {
        const reihe = ['k1', 'k2']
        const opt = { planungsart: 'sequenz', kapitelVon: { s1: 'k1', s3: 'k2' } }
        expect(abschnittFarbe({ sequenz_ids: ['s3', 's1'], kapitel_ids: ['k1'] }, reihe, opt)).toBe(ueColorIndex(1))
        expect(abschnittFarbe({ sequenz_ids: ['fremd'] }, reihe, opt)).toBeNull()
    })
})

describe('Planungsart (Schritt 7)', () => {
    const CURRICULA = [{ kapitel: [
        { id: 'k1', titel: 'Ähnlichkeit', std: 12, sequenzen: [{ id: 's1', titel: 'Strahlensätze', std: 6 }] },
        { id: 'k2', titel: 'Pythagoras', std: 20, sequenzen: [] },
    ] }]
    it('Bezugsfeld', () => {
        expect(bezugsfeld('sequenz')).toBe('sequenz_ids')
        expect(bezugsfeld('kapitel')).toBe('kapitel_ids')
        expect(bezugsfeld(undefined)).toBe('kapitel_ids')
    })
    it('Einheiten der Curricula', () => {
        const e = einheiten(CURRICULA)
        expect(e.kapitelReihenfolge).toEqual(['k1', 'k2'])
        expect(e.kapitelVon).toEqual({ s1: 'k1' })
        expect([e.titel.s1, e.std.s1, e.std.k2]).toEqual(['Strahlensätze', 6, 20])
        expect(einheiten(undefined).kapitelReihenfolge).toEqual([])
    })
    it('Dauervorschlag aus Stunden', () => {
        expect(dauerVorschlag(8, 4)).toBe(2)
        expect(dauerVorschlag(6, 4)).toBe(2)
        expect(dauerVorschlag(1, 4)).toBe(1)
        expect(dauerVorschlag(null, 4)).toBeNull()
        expect(dauerVorschlag(8, null)).toBeNull()
    })
    it('Bezugstext je Planungsart', () => {
        const { titel } = einheiten(CURRICULA)
        const a = { sequenz_ids: ['s1', 'weg'], kapitel_ids: ['k2'] }
        expect(bezugText(a, 'sequenz', titel)).toBe('Strahlensätze, nicht mehr im Curriculum')
        expect(bezugText(a, 'kapitel', titel)).toBe('Pythagoras')
    })
})

describe('Anlegen und Liste', () => {
    it('neuer Abschnitt: eine Woche, ohne Bezüge', () => {
        expect(neuerAbschnitt()).toEqual({ id: null, titel: '', wochen: 1, kapitel_ids: [], sequenz_ids: [], notiz: '' })
    })
    it('laufendes und nächstes Schuljahr', () => {
        expect(schuljahreZumAnlegen('2025/26')).toEqual(['2025/26', '2026/27'])
        expect(schuljahreZumAnlegen('2099/00')).toEqual(['2099/00', '2100/01'])
        expect(schuljahreZumAnlegen(undefined)).toEqual([])
    })
    it('teilt in laufend und Archiv', () => {
        const { aktuell, archiv } = teilen([
            { id: 1, schuljahr: '2026/27', stufe: 7 },
            { id: 2, schuljahr: '2025/26', stufe: 9 },
            { id: 3, schuljahr: '2025/26', stufe: 7 },
            { id: 4, schuljahr: '2023/24', stufe: 7, archiviert: true },
            { id: 5, schuljahr: '2024/25', stufe: 7, archiviert: true },
        ])
        expect(aktuell.map((p) => p.id)).toEqual([3, 2, 1])
        expect(archiv.map((p) => p.id)).toEqual([5, 4])
    })
})

describe('Bilanz', () => {
    it('mit Spielraum einer Wochenstunde', () => {
        expect(bilanzStand({ soll: 12, geplant: 16 }, 4)).toBe('passt')
        expect(bilanzStand({ soll: 12, geplant: 17 }, 4)).toBe('zu viel')
        expect(bilanzStand({ soll: 20, geplant: 12 }, 4)).toBe('zu wenig')
        expect(bilanzStand({ soll: null, geplant: 4 }, 4)).toBeNull()
        expect(bilanzStand({ soll: 4, geplant: null }, null)).toBeNull()
    })
})

describe('Speichern', () => {
    it('nur die gespeicherten Felder', () => {
        const aus = zumSpeichern([{ id: 'x', titel: 'A', wochen: '3', kapitel_ids: ['k'], notiz: '', von_woche: 1 }], 'sequenz')
        expect(aus).toEqual({ planungsart: 'sequenz', abschnitte: [{ id: 'x', titel: 'A', wochen: 3, kapitel_ids: ['k'], sequenz_ids: [], notiz: '' }] })
    })
})

describe('Übernehmen (Schritt 6)', () => {
    it('Ziele: laufendes und nächstes, ohne das eigene', async () => {
        const { uebernahmeZiele } = await import('./verlaufsplan.js')
        expect(uebernahmeZiele('2025/26', '2024/25')).toEqual(['2025/26', '2026/27'])
        expect(uebernahmeZiele('2025/26', '2025/26')).toEqual(['2026/27'])
    })
    it('Ausgangspunkte: gleiches Fach und gleiche Stufe, anderes Jahr, neueste zuerst', async () => {
        const { ausgangspunkte } = await import('./verlaufsplan.js')
        const plaene = [
            { id: 1, subject_id: 3, stufe: 9, schuljahr: '2023/24' },
            { id: 2, subject_id: 3, stufe: 9, schuljahr: '2024/25' },
            { id: 3, subject_id: 3, stufe: 9, schuljahr: '2025/26' },
            { id: 4, subject_id: 3, stufe: 8, schuljahr: '2024/25' },
            { id: 5, subject_id: 4, stufe: 9, schuljahr: '2024/25' },
        ]
        expect(ausgangspunkte(plaene, 3, 9, '2025/26').map((p) => p.id)).toEqual([2, 1])
        expect(ausgangspunkte(plaene, 3, NaN, '2025/26')).toEqual([])
        expect(ausgangspunkte(plaene, 3, 0, '2025/26')).toEqual([])
    })
})
