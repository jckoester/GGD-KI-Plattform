import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { einplanAnfrage, einplanbareTermine, heuteIso, terminText } from './einplanen.js'

const SRC = join(__dirname, '..')
const quelle = (pfad) => readFileSync(join(SRC, pfad), 'utf8')

const slot = (id, date, rest = {}) => ({
    id, date, kategorie: 'unterricht', ue_node_id: null, stunde_node_id: null, thema: null,
    start_period: null, periods: 1, updated_at: `t-${id}`, ...rest,
})

describe('einplanbareTermine (F1)', () => {
    const slots = [
        slot('frei-spaet', '2026-10-02'),
        slot('frei-frueh', '2026-09-20'),
        slot('vorbei', '2026-09-01'),
        slot('eigen', '2026-09-25', { ue_node_id: 'u1', thema: 'Getriebe' }),
        slot('fremd', '2026-09-21', { ue_node_id: 'u2' }),
        slot('belegt', '2026-09-22', { stunde_node_id: 'x' }),
        slot('ausfall', '2026-09-23', { kategorie: 'ausfall' }),
        slot('heute', '2026-09-15', { start_period: 3 }),
        slot('heute-frueher', '2026-09-15', { start_period: 1 }),
    ]

    it('erst Termine der Einheit, dann leere; ab heute, ohne Entwurf, nur Unterricht', () => {
        const { eigene, freie } = einplanbareTermine(slots, 'u1', '2026-09-15')
        expect(eigene.map((s) => s.id)).toEqual(['eigen'])
        expect(freie.map((s) => s.id)).toEqual(['heute-frueher', 'heute', 'frei-frueh', 'frei-spaet'])
    })

    it('Stunde ohne Einheit: nur leere Termine', () => {
        const { eigene, freie } = einplanbareTermine(slots, null, '2026-09-15')
        expect(eigene).toEqual([])
        expect(freie.map((s) => s.id)).not.toContain('eigen')
    })
})

describe('einplanAnfrage', () => {
    const stunde = { id: 's1', titel: 'Zahnräder' }

    it('leerer Termin: Einheit und Titel als Thema mitgeben, Stand mitschicken', () => {
        expect(einplanAnfrage(slot('a', '2026-09-20'), stunde, 'u1')).toEqual({
            stunde_node_id: 's1', expected_updated_at: 't-a', ue_node_id: 'u1', thema: 'Zahnräder',
        })
    })

    it('Termin der Einheit mit Thema: beides bleibt', () => {
        expect(einplanAnfrage(slot('b', '2026-09-20', { ue_node_id: 'u1', thema: 'Getriebe' }), stunde, 'u1'))
            .toEqual({ stunde_node_id: 's1', expected_updated_at: 't-b' })
    })

    it('Stunde ohne Einheit: keine Einheit setzen', () => {
        expect(einplanAnfrage(slot('c', '2026-09-20'), stunde, null)).not.toHaveProperty('ue_node_id')
    })
})

describe('Kleinkram', () => {
    it('heute in Ortszeit', () => {
        expect(heuteIso(new Date(2026, 8, 5, 23, 30))).toBe('2026-09-05')
    })

    it('Terminbeschriftung', () => {
        expect(terminText(slot('a', '2026-09-15', { start_period: 3 }))).toBe('Di 15.9., 3. Std.')
        expect(terminText(slot('a', '2026-09-15', { start_period: 3, periods: 2, thema: 'Getriebe' })))
            .toBe('Di 15.9., 3./4. Std. · Getriebe')
        expect(terminText(slot('a', '2026-09-15'))).toBe('Di 15.9.')
    })
})

describe('Verdrahtung', () => {
    it('Einheitenansicht und Stundenentwurf bieten „Einplanen“ an', () => {
        expect(quelle('lib/components/planner/EinheitenAnsicht.svelte')).toContain('onEinplanen(s, einheit)')
        const planer = quelle('routes/(app)/subjects/[slug]/groups/[id]/planner/+page.svelte')
        expect(planer).toContain('<EinplanenDialog')
        expect(planer).toMatch(/onEinplanen=\{/)
        const entwurf = quelle('routes/(app)/subjects/[slug]/groups/[id]/planner/lessons/[nodeId]/+page.svelte')
        expect(entwurf).toContain('<EinplanenDialog')
        expect(entwurf).toMatch(/!lesson\.slot && !nurLesen/)
    })
})
