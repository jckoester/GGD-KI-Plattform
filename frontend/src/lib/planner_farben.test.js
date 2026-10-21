/**
 * Keine rohen Palettenwerte in den Planer-Komponenten (0.21, Päckchen H; CLAUDE.md
 * „Semantische Farb-Tokens"). Umgestellt am 21.10.2026, hell und dunkel im Browser geprüft.
 */
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const ORDNER = join(import.meta.dirname, 'components/planner')
const ROH = /\b(?:bg|text|border|ring|from|to|via)-(?:base|blue|red|green|yellow|orange|purple|cyan|magenta)-\d{2,3}\b|var\(--color-(?:base|blue|red|green|yellow|orange|purple|cyan|magenta)-\d/

describe('planner/: nur semantische Farb-Tokens', () => {
    const dateien = readdirSync(ORDNER).filter((n) => n.endsWith('.svelte'))

    it('findet die Komponenten überhaupt', () => {
        expect(dateien.length).toBeGreaterThanOrEqual(10)
    })

    it('keine rohe Palette außerhalb von Kommentaren', () => {
        const funde = []
        for (const name of dateien) {
            readFileSync(join(ORDNER, name), 'utf8').split('\n').forEach((zeile, i) => {
                const ohneKommentar = zeile.replace(/^\s*(\*|\/\/|<!--).*$/, '')
                if (ROH.test(ohneKommentar)) funde.push(`${name}:${i + 1}: ${zeile.trim()}`)
            })
        }
        expect(funde).toEqual([])
    })
})
