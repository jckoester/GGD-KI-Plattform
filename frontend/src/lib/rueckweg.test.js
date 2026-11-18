/**
 * Rückweg aus `?back=` (0.47.1): nur Pfade der Plattform, und jede Seite liest den Parameter
 * über `rueckwegAus` — ungeprüft im `href` war `?back=javascript:…` ausführbar.
 */
import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { rueckwegAus, sichererRueckweg } from './rueckweg.js'

describe('sichererRueckweg', () => {
    it('lässt Pfade der Plattform samt Query und Anker durch', () => {
        for (const pfad of [
            '/knowledge',
            '/knowledge/search?q=Optik&typ=begriff',
            '/chat?id=42',
            '/knowledge/curriculum/abc#kapitel-2',
            '/help/erste-schritte#die-einrichtung-schülerinnen',
        ]) {
            expect(sichererRueckweg(pfad)).toBe(pfad)
        }
    })

    it('weist Skript, fremde Seiten und Tricks ab', () => {
        for (const wert of [
            'javascript:alert(1)',
            'JavaScript:alert(1)',
            ' javascript:alert(1)',
            'data:text/html,<script>alert(1)</script>',
            'https://fremd.example',
            '//fremd.example',
            '/\\fremd.example',
            '/\t/fremd.example',
            '/\n/fremd.example',
            '\\\\fremd.example',
            'knowledge',
            '',
        ]) {
            expect(sichererRueckweg(wert), JSON.stringify(wert)).toBeNull()
        }
    })

    it('verträgt fehlende Werte', () => {
        expect(sichererRueckweg(null)).toBeNull()
        expect(sichererRueckweg(undefined)).toBeNull()
        expect(rueckwegAus(new URLSearchParams(''))).toBeNull()
        expect(rueckwegAus(new URLSearchParams('back=%2Fknowledge%2Fmine'))).toBe('/knowledge/mine')
        expect(rueckwegAus(new URLSearchParams('back=javascript%3Aalert(1)'))).toBeNull()
    })
})

// src/lib → src
const SRC = dirname(dirname(fileURLToPath(import.meta.url)))

function dateien(ordner) {
    return readdirSync(ordner).flatMap((name) => {
        const pfad = join(ordner, name)
        if (statSync(pfad).isDirectory()) return dateien(pfad)
        return /\.(svelte|js)$/.test(name) && !name.endsWith('.test.js') ? [pfad] : []
    })
}

describe('Wächter: `back` nur über rueckwegAus', () => {
    it('keine Seite liest den Parameter ungeprüft', () => {
        const roh = /searchParams\.get\(\s*['"`]back['"`]\s*\)/
        const funde = dateien(SRC)
            .filter((pfad) => !pfad.endsWith('rueckweg.js'))
            .filter((pfad) => roh.test(readFileSync(pfad, 'utf8')))
            .map((pfad) => relative(SRC, pfad))
        expect(funde).toEqual([])
    })
})
