/**
 * Wächter: Zurück ist ein Link mit festem Ziel (0.48, Päckchen N, F3 a / G1).
 *
 * Bis 0.47 gingen 18 Seiten per `history.back()` zurück: in einem neuen Tab nirgends hin,
 * sonst dorthin, wo man zufällig vorher war (Beta-Rückmeldung 12.10.2026). Quelltext statt
 * Verhalten, wie in `sidebar_navigation.test.js`.
 */
import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const SRC = dirname(dirname(fileURLToPath(import.meta.url)))
const lies = (rel) => readFileSync(join(SRC, rel), 'utf8')

function dateien(ordner) {
    return readdirSync(ordner).flatMap((name) => {
        const pfad = join(ordner, name)
        if (statSync(pfad).isDirectory()) return dateien(pfad)
        return /\.(svelte|js)$/.test(name) && !name.endsWith('.test.js') ? [pfad] : []
    })
}

describe('Zurück', () => {
    it('history.back() nur in ZurueckLink (dort nur mit `echt`)', () => {
        const funde = dateien(SRC)
            .map((p) => relative(SRC, p))
            .filter((rel) => rel !== join('lib', 'components', 'ZurueckLink.svelte'))
            .filter((rel) => /history\.back\(\)/.test(lies(rel)))
        expect(funde).toEqual([])
    })

    it.each([
        'routes/(admin)/budget/+page.svelte',
        'routes/(admin)/flags/+page.svelte',
        'routes/(admin)/settings/+page.svelte',
        'routes/(admin)/statistics/+page.svelte',
        'routes/(app)/history/+page.svelte',
    ])('%s steht in der Seitenleiste und braucht kein Zurück (G1)', (rel) => {
        expect(lies(rel)).not.toContain('ZurueckLink')
    })

    it.each(['routes/(app)/profile/+page.svelte', 'routes/(app)/teaching/+page.svelte'])(
        '%s schließt auf die Startseite',
        (rel) => {
            expect(lies(rel)).toContain('<ZurueckLink href="/welcome" schliessen />')
        },
    )

    it.each([
        ['routes/(admin)/settings/audit/+page.svelte', '/settings'],
        ['routes/(admin)/settings/texts/+page.svelte', '/settings'],
        ['routes/(admin)/statistics/costs/+page.svelte', '/statistics'],
        ['routes/(app)/knowledge/curricula/+page.svelte', '/knowledge'],
        ['routes/(app)/knowledge/year-plans/+page.svelte', '/knowledge'],
        ['routes/(app)/knowledge/education-plans/+page.svelte', '/knowledge'],
        ['routes/(app)/knowledge/collections/[type]/+page.svelte', '/knowledge'],
    ])('%s führt auf die Oberseite %s', (rel, ziel) => {
        expect(lies(rel)).toContain(`<ZurueckLink href="${ziel}"`)
    })

    it('von Baustein zu Baustein: echtes Zurück', () => {
        expect(lies('routes/(app)/knowledge/[id]/+page.svelte')).toContain('<ZurueckLink href={backUrl} echt />')
    })

    it('ZurueckLink geht nur mit `echt` und Vorgänger im Tab per history.back(), Modifikatoren öffnen den Link', () => {
        const z = lies('lib/components/ZurueckLink.svelte')
        expect(z).toContain('if (!echt || !vorgaenger) return;')
        expect(z).toMatch(/e\.metaKey \|\| e\.ctrlKey/)
        expect(z).toMatch(/afterNavigate\(\(\{ from \}\)/)
    })
})
