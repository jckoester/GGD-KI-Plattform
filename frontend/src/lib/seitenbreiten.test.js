/**
 * Wächter: zwei Seitenbreiten (0.48, Päckchen N, G6–G8).
 *
 * Vorher gab es neun Höchstbreiten von `2xl` bis volle Breite (Jan, 18.11.2026: „unterscheiden
 * sich stark“). Seiten nehmen `PageBody` (schmal `4xl`, breit `7xl`); einen eigenen zentrierten
 * Rahmen haben nur die Ausnahmen unten.
 */
import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROUTES = join(dirname(fileURLToPath(import.meta.url)), '..', 'routes')

function seiten(ordner = ROUTES) {
    return readdirSync(ordner).flatMap((name) => {
        const pfad = join(ordner, name)
        if (statSync(pfad).isDirectory()) return seiten(pfad)
        return name === '+page.svelte' ? [pfad] : []
    })
}

// Eigener Rahmen, aber in einer der zwei Breiten — mit Grund.
const AUSNAHMEN = {
    '(app)/chat/+page.svelte': 'Chatspalte mit fester Eingabe unten',
    '(app)/knowledge/search/+page.svelte': 'eigener Scrollbereich wegen der Auswahlleiste',
    '(app)/subjects/[slug]/groups/[id]/planner/+page.svelte': 'Planer mit eigener Struktur',
    '(app)/help/+page.svelte': 'Layout mit Inhaltsverzeichnis scrollt selbst',
    '(app)/help/[seite]/+page.svelte': 'Layout mit Inhaltsverzeichnis scrollt selbst',
    'info/[key]/+page.svelte': 'außerhalb des App-Layouts',
}

describe('Seitenbreiten', () => {
    const rahmen = /class="[^"]*(?:max-w-(\S+)[^"]*mx-auto|mx-auto[^"]*max-w-(\S+))/g

    it('kein zentrierter Seitenrahmen außer den Ausnahmen', () => {
        const funde = seiten()
            .map((p) => relative(ROUTES, p))
            .filter((rel) => !(rel in AUSNAHMEN))
            // Ohne `g`: `test` mit `g` merkt sich `lastIndex` und überspränge Dateien.
            .filter((rel) => new RegExp(rahmen.source).test(readFileSync(join(ROUTES, rel), 'utf8')))
        expect(funde).toEqual([])
    })

    it('die Ausnahmen halten sich an die zwei Breiten', () => {
        for (const rel of Object.keys(AUSNAHMEN)) {
            const quelle = readFileSync(join(ROUTES, rel), 'utf8')
            for (const m of quelle.matchAll(rahmen)) {
                expect(['4xl', '7xl'], rel).toContain((m[1] ?? m[2]).replace(/"$/, ''))
            }
        }
    })

    it('PageBody kennt genau zwei Breiten', () => {
        const pb = readFileSync(join(ROUTES, '..', 'lib', 'components', 'PageBody.svelte'), 'utf8')
        expect(pb).toContain("{breit ? 'max-w-7xl' : 'max-w-4xl'} mx-auto")
    })

    it('der Admin-Bereich scrollt nicht selbst (G7 a)', () => {
        const layout = readFileSync(join(ROUTES, '(admin)', '+layout.svelte'), 'utf8')
        expect(layout).toMatch(/<main\s+class="flex-1 overflow-hidden/)
    })

    it('Hilfe und Infoseiten halten die Textspalte auf Lesebreite (G8 a)', () => {
        for (const rel of ['(app)/help/+page.svelte', '(app)/help/[seite]/+page.svelte', 'info/[key]/+page.svelte']) {
            expect(readFileSync(join(ROUTES, rel), 'utf8'), rel).toContain('prose dark:prose-invert max-w-prose')
        }
    })

    it('Startseite schmal wie PageBody, Meine Bausteine breit (G9, 18.11.2026)', () => {
        const start = readFileSync(join(ROUTES, '(app)', 'welcome', '+page.svelte'), 'utf8')
        expect(start).toContain('class="w-full max-w-4xl px-6 flex flex-col gap-6"')
        const mine = readFileSync(join(ROUTES, '(app)', 'knowledge', 'mine', '+page.svelte'), 'utf8')
        expect(mine).toContain('<PageBody breit>')
    })
})
