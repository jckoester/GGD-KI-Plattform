/**
 * Gemeinsamer Dialog-Rahmen (0.21, Päckchen H, F1 a).
 *
 * Das Verhalten — Fokus hinein, Tab im Kreis, Escape, Fokus zurück — ist im Browser mit echten
 * Tasten geprüft (Firefox, 21.10.2026, `Plaene/Messungen-0.21/dialoge.py`). Hier gehalten wird,
 * dass die Planer-Dialoge den Rahmen benutzen, statt wieder einen eigenen zu bauen.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const KOMP = join(import.meta.dirname, 'components')
const lies = (p) => readFileSync(join(KOMP, p), 'utf8')

describe('Dialog.svelte', () => {
    const rahmen = lies('Dialog.svelte')

    it('trägt Rolle, Modalität und Überschrift', () => {
        expect(rahmen).toContain('role="dialog"')
        expect(rahmen).toContain('aria-modal="true"')
        expect(rahmen).toContain('aria-labelledby={titelId}')
    })

    it('führt den Fokus: hinein, im Kreis, zurück', () => {
        expect(rahmen).toMatch(/ziel\.focus\(\)/)
        expect(rahmen).toContain("e.key === 'Tab'")
        expect(rahmen).toContain("e.key === 'Escape'")
        expect(rahmen).toMatch(/vorher !== document\.body/)
        expect(rahmen).toContain('fokusZurueck?.()')
    })
})

describe.each(['planner/UnitDialog.svelte', 'planner/AusfallDialog.svelte', 'planner/PatternEditor.svelte'])(
    '%s', (datei) => {
        const quelle = lies(datei)

        it('benutzt den gemeinsamen Rahmen', () => {
            expect(quelle).toContain("import Dialog from '$lib/components/Dialog.svelte'")
            expect(quelle).toMatch(/<Dialog\b[^>]*titelId="[\w-]+"/)
        })

        it('baut keinen eigenen Rahmen mehr', () => {
            expect(quelle).not.toContain('role="dialog"')
            expect(quelle).not.toContain('role="presentation"')
        })

        it('die Überschrift trägt die Kennung aus titelId', () => {
            const id = /titelId="([\w-]+)"/.exec(quelle)[1]
            expect(quelle).toContain(`<h2 id="${id}"`)
        })
    })
