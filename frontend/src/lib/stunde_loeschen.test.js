import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { loeschbar, loeschFrage } from './stunde_loeschen.js'

const SRC = join(__dirname, '..')
const quelle = (pfad) => readFileSync(join(SRC, pfad), 'utf8')

describe('Stunde löschen (0.42.4)', () => {
    it('nur eigene, nicht nachbereitete Stunden', () => {
        expect(loeschbar({ eigen: true, nachbereitet: false })).toBe(true)
        expect(loeschbar({ eigen: false, nachbereitet: false })).toBe(false)
        expect(loeschbar({ eigen: true, nachbereitet: true })).toBe(false)
        expect(loeschbar(null)).toBe(false)
    })

    it('Rückfrage nennt den Termin, wenn es einen gibt', () => {
        expect(loeschFrage('Getriebe')).toBe('Stunde „Getriebe“ endgültig löschen? Das lässt sich nicht rückgängig machen.')
        expect(loeschFrage('Getriebe', '2026-09-15')).toContain('für Di 15.9. eingeplant')
    })

    it('Verdrahtung: Einheitenansicht, Planer und Stundenentwurf', () => {
        expect(quelle('lib/components/planner/EinheitenAnsicht.svelte')).toMatch(/onLoeschen && loeschbar\(s\)/)
        const planer = quelle('routes/(app)/subjects/[slug]/groups/[id]/planner/+page.svelte')
        // Eigener Dialog, kein `confirm` (Wächter in ausfall.test.js).
        expect(planer).toContain('<LoeschenDialog')
        expect(planer).toMatch(/onLoeschen=\{loescheStunde\}/)
        const entwurf = quelle('routes/(app)/subjects/[slug]/groups/[id]/planner/lessons/[nodeId]/+page.svelte')
        expect(entwurf).toContain('lesson.darf_loeschen')
        expect(entwurf).toContain('<LoeschenDialog')
        expect(quelle('lib/components/planner/LoeschenDialog.svelte')).toContain('loeschFrage(')
        // Kein Autospeichern mehr nach dem Löschen (sonst 404 auf einen gelöschten Entwurf).
        expect(entwurf).toMatch(/async function loeschen\(\) \{[\s\S]*?clearTimeout\(saveTimer\)/)
    })
})
