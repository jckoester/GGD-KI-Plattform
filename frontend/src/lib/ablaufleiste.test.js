import { describe, expect, it } from 'vitest'
import { TITEL_AB_WOCHEN, bloecke, ferienKurz, freiStuecke, heuteSpalte, monate, raster } from './ablaufleiste.js'

// Kleines Schuljahr: 6 Unterrichtswochen, Herbstferien nach Woche 2, Weihnachten nach Woche 4
const LAGE = {
    unterrichtswochen: 6,
    belegt: 5,
    wochen: [
        { nr: 1, montag: '2025-09-29' },
        { nr: 2, montag: '2025-10-06' },
        { nr: 3, montag: '2025-10-20' },  // Herbstferien 13.–19.10.
        { nr: 4, montag: '2025-10-27' },
        { nr: 5, montag: '2026-01-12' },  // Weihnachtsferien dazwischen
        { nr: 6, montag: '2026-01-19' },
    ],
    ferien: [
        { name: 'Herbstferien', von: '2025-10-13', bis: '2025-10-19', nach_woche: 2 },
        { name: 'Weihnachtsferien', von: '2025-11-03', bis: '2026-01-11', nach_woche: 4 },
    ],
    abschnitte: [
        { nr: 1, von_woche: 1, bis_woche: 3 },   // über die Herbstferien: 2 + 1
        { nr: 2, von_woche: 4, bis_woche: 5 },   // über Weihnachten: 1 + 1
    ],
}

describe('Raster', () => {
    it('setzt Ferien als eigene Spalte zwischen die Wochen', () => {
        const r = raster(LAGE)
        expect(r.spalten.map((s) => (s.art === 'woche' ? s.nr : s.kurz))).toEqual([1, 2, 'Herbst', 3, 4, 'Weihnachts', 5, 6])
        expect(r.spalteVon).toEqual({ 1: 1, 2: 2, 3: 4, 4: 5, 5: 7, 6: 8 })
    })

    it('teilt einen Bereich an den Ferien', () => {
        const r = raster(LAGE)
        expect(r.stuecke(1, 3)).toEqual([{ von: 1, bis: 3, wochen: 2 }, { von: 4, bis: 5, wochen: 1 }])
        expect(r.stuecke(5, 6)).toEqual([{ von: 7, bis: 9, wochen: 2 }])
    })

    it('hängt Überhangwochen ohne Lücke an', () => {
        const r = raster({ ...LAGE, belegt: 8 })
        expect(r.spalten.slice(-2)).toEqual([{ art: 'woche', nr: 7, ueberhang: true }, { art: 'woche', nr: 8, ueberhang: true }])
    })

    it('Ferien nach der letzten Woche sind keine Lücke', () => {
        const r = raster({ ...LAGE, ferien: [...LAGE.ferien, { name: 'Sommerferien', nach_woche: 6 }] })
        expect(r.spalten.at(-1)).toEqual({ art: 'woche', nr: 6, ueberhang: false })
    })

    it('Kurznamen', () => {
        expect(ferienKurz('Pfingstferien')).toBe('Pfingst')
        expect(ferienKurz('Bewegliche Tage')).toBe('Bewegliche Tage')
    })
})

describe('Blöcke', () => {
    it('Titel im breitesten Stück, ab drei Wochen; sonst die Nummer', () => {
        const r = raster(LAGE)
        const [a, b] = bloecke(LAGE, r)
        expect(a.stuecke.map((s) => s.beschriftung)).toEqual(['nummer', null])
        expect(b.stuecke.map((s) => s.beschriftung)).toEqual(['nummer', null])
        const lang = bloecke({ ...LAGE, abschnitte: [{ nr: 1, von_woche: 3, bis_woche: 6 }] }, r)[0]
        expect(lang.stuecke.map((s) => [s.wochen, s.beschriftung])).toEqual([[2, 'nummer'], [2, null]])
        expect(TITEL_AB_WOCHEN).toBe(3)
        const ohneFerien = bloecke({ ...LAGE, ferien: [], abschnitte: [{ nr: 1, von_woche: 1, bis_woche: 3 }] }, raster({ ...LAGE, ferien: [] }))[0]
        expect(ohneFerien.stuecke).toEqual([{ von: 1, bis: 4, wochen: 3, beschriftung: 'titel' }])
    })

    it('freie Wochen am Ende, beschriftet im breitesten Stück', () => {
        const r = raster(LAGE)
        expect(freiStuecke(LAGE, r)).toEqual([{ von: 8, bis: 9, wochen: 1, beschriftet: true }])
        expect(freiStuecke({ ...LAGE, belegt: 6 }, r)).toEqual([])
    })
})

describe('Achsen', () => {
    it('Monat am Donnerstag der Woche', () => {
        const r = raster(LAGE)
        // Woche 1 (29.09.) hat ihren Donnerstag am 02.10. → Okt
        expect(monate(LAGE, r.spalteVon)).toEqual([{ spalte: 1, text: 'Okt' }, { spalte: 7, text: 'Jan' }])
    })

    it('heute in einer Woche, in den Ferien, außerhalb', () => {
        const r = raster(LAGE)
        expect(heuteSpalte(LAGE, r, new Date(2025, 9, 8))).toEqual({ spalte: 2 })
        expect(heuteSpalte(LAGE, r, new Date(2025, 9, 15))).toEqual({ spalte: 3 })    // Herbstferien
        expect(heuteSpalte(LAGE, r, new Date(2025, 11, 24))).toEqual({ spalte: 6 })   // Weihnachten
        expect(heuteSpalte(LAGE, r, new Date(2025, 8, 1))).toBeNull()
        expect(heuteSpalte(LAGE, r, new Date(2026, 1, 1))).toBeNull()
        expect(heuteSpalte({}, r)).toBeNull()
    })
})
