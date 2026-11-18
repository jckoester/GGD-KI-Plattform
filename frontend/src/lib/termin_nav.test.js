/** Stunden-Navigation nach Terminen (0.48, Päckchen N, F4–F6). */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { einheitKnopfZeigen, terminKurz, terminTitel } from './termin_nav.js'

const termin = (x = {}) => ({
    slot_id: 's1', datum: '2026-11-13', start_period: 3, kategorie: 'unterricht',
    thema: null, stunde_node_id: 'n1', ...x,
})

describe('terminKurz', () => {
    it('Wochentag und Datum ohne Jahr', () => {
        expect(terminKurz(termin())).toBe('Fr 13.11.')
        expect(terminKurz(termin({ datum: '2026-12-01' }))).toBe('Di 01.12.')
        expect(terminKurz(null)).toBe('')
    })
})

describe('terminTitel', () => {
    it('nennt Stunde, Thema und Prüfung', () => {
        expect(terminTitel(termin({ thema: 'Redox', kategorie: 'pruefung' }), 'nachher'))
            .toBe('Nächster Termin: Fr 13.11., 3. Stunde · Prüfung · Redox')
    })

    it('sagt, dass der Klick einen Entwurf anlegt (F4 b)', () => {
        expect(terminTitel(termin({ stunde_node_id: null }), 'vorher'))
            .toMatch(/^Voriger Termin: .*noch kein Entwurf — Klick legt ihn an$/)
    })
})

describe('einheitKnopfZeigen (F6 a)', () => {
    it('zeigt den Einheiten-Knopf nur, wenn er woandershin führt', () => {
        expect(einheitKnopfZeigen('n1', termin())).toBe(false)
        expect(einheitKnopfZeigen('n2', termin())).toBe(true)
        expect(einheitKnopfZeigen('n2', null)).toBe(true)
        expect(einheitKnopfZeigen(null, termin())).toBe(false)
    })
})

describe('Entwurfsansicht', () => {
    const SEITE = readFileSync(
        join(dirname(fileURLToPath(import.meta.url)), '..', 'routes', '(app)', 'subjects', '[slug]',
            'groups', '[id]', 'planner', 'lessons', '[nodeId]', '+page.svelte'),
        'utf8',
    )

    it('legt einen fehlenden Entwurf über den Termin an, Modifikatoren öffnen den Link', () => {
        expect(SEITE).toContain('createLessonForSlot(t.slot_id)')
        expect(SEITE).toMatch(/if \(t\.stunde_node_id \|\| e\.button !== 0 \|\| e\.metaKey/)
    })

    it('frischt die Termine nach dem Einplanen mit auf', () => {
        expect(SEITE).toContain('termine: frisch.termine')
    })
})
