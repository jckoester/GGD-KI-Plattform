import { describe, expect, it } from 'vitest'
import {
    einrichtungsRolle, fortschritt, seitenNummer, sichtbareSeiten, sollAufgehen, startIndex,
    SEITEN, SEITEN_JE_ROLLE,
} from './einrichtung.js'

const mitPlan = { stundenplan: { configured: true } }
const ohnePlan = { stundenplan: { configured: false } }

describe('Rolle (F10)', () => {
    it('Lehrkraft, auch mit Admin; reiner Admin und Schüler:in nicht', () => {
        expect(einrichtungsRolle(['teacher'])).toBe('teacher')
        expect(einrichtungsRolle(['teacher', 'admin'])).toBe('teacher')
        expect(einrichtungsRolle(['admin'])).toBeNull()
        expect(einrichtungsRolle(['student'])).toBeNull()
        expect(einrichtungsRolle(undefined)).toBeNull()
    })

    it('jede Seite einer Rolle hat einen Titel', () => {
        for (const seiten of Object.values(SEITEN_JE_ROLLE)) {
            for (const s of seiten) expect(SEITEN[s]?.titel, s).toBeTruthy()
        }
    })
})

describe('Seiten', () => {
    it('sechs mit Stundenplanquelle, fünf ohne', () => {
        expect(sichtbareSeiten('teacher', mitPlan)).toHaveLength(6)
        expect(sichtbareSeiten('teacher', ohnePlan)).not.toContain('stundenplan')
        expect(sichtbareSeiten('teacher', ohnePlan)).toHaveLength(5)
        expect(sichtbareSeiten(null, mitPlan)).toEqual([])
    })

    it('Nummer in der vollen Liste, Anzeige in der gezeigten', () => {
        expect(seitenNummer('teacher', 'gruppen')).toBe(5)
        const seiten = sichtbareSeiten('teacher', ohnePlan)
        expect(fortschritt(seiten.indexOf('gruppen'), seiten)).toBe('4 von 5')
    })
})

describe('Wiedereinstieg', () => {
    const seiten = sichtbareSeiten('teacher', mitPlan)

    it('nach „später“ dort, wo der Durchgang stand', () => {
        expect(seiten[startIndex('teacher', seiten, { stand: 'spaeter', seite: 3 })]).toBe('stufe')
    })

    it('entfallene Seite: die nächste gezeigte', () => {
        const ohne = sichtbareSeiten('teacher', ohnePlan)
        expect(ohne[startIndex('teacher', ohne, { stand: 'spaeter', seite: 4 })]).toBe('gruppen')
    })

    it('neu, erledigt oder abgewählt: von vorn', () => {
        expect(startIndex('teacher', seiten, { stand: null, seite: null })).toBe(0)
        expect(startIndex('teacher', seiten, { stand: 'erledigt', seite: 6 })).toBe(0)
        expect(startIndex('teacher', seiten, { stand: 'abgewaehlt', seite: 2 })).toBe(0)
    })
})

describe('Von selbst aufgehen (F3)', () => {
    it('auf jeder Seite, nur nicht in der Hilfe', () => {
        expect(sollAufgehen({ faellig: true }, '/chat')).toBe(true)
        expect(sollAufgehen({ faellig: true }, '/subjects/chemie/groups/3')).toBe(true)
        expect(sollAufgehen({ faellig: true }, '/help/chat')).toBe(false)
        expect(sollAufgehen({ faellig: false }, '/chat')).toBe(false)
        expect(sollAufgehen(null, '/chat')).toBe(false)
    })
})

describe('Verdrahtung', () => {
    it('einmal im Layout, über den Store geschaltet', async () => {
        const { readFileSync } = await import('node:fs')
        const { join } = await import('node:path')
        const layout = readFileSync(join(__dirname, '..', 'routes/(app)/+layout.svelte'), 'utf8')
        expect(layout).toContain('<EinrichtungDialog')
        expect(layout).toContain('sollAufgehen($einrichtung.daten, $page.url.pathname)')
        expect(layout).toMatch(/if \(einrichtungsRolle_\) ladeEinrichtung\(\)/)
    })

    it('Später speichert die Seite, die letzte Seite „erledigt“', async () => {
        const { readFileSync } = await import('node:fs')
        const { join } = await import('node:path')
        const dialog = readFileSync(join(__dirname, 'components/EinrichtungDialog.svelte'), 'utf8')
        expect(dialog).toContain("putEinrichtung('spaeter', seitenNummer(rolle, seite))")
        expect(dialog).toContain("putEinrichtung('erledigt', seitenNummer(rolle, seite))")
        expect(dialog).toContain('<Dialog open onClose={schliessen}')
    })
})
