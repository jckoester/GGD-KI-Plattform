/**
 * Knopf „Aktuelle Woche" im Jahresplan (0.21, Päckchen H, F4) — und derselbe Sprung beim
 * Öffnen der Planung.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import { groupSlotsByWeek, wochenSchluessel, zielwoche } from './planner.js'

const SRC = join(import.meta.dirname, '..')

describe('zielwoche', () => {
    const liste = ['2026-W41', '2026-W42', '2026-W45', '2026-W46']

    it('nimmt die Woche von heute', () => {
        expect(zielwoche(liste, '2026-W42')).toBe('2026-W42')
    })

    it('in den Ferien die nächste Unterrichtswoche', () => {
        expect(zielwoche(liste, '2026-W44')).toBe('2026-W45')
    })

    it('nach dem letzten Termin die letzte Woche, davor die erste', () => {
        expect(zielwoche(liste, '2027-W30')).toBe('2026-W46')
        expect(zielwoche(liste, '2026-W30')).toBe('2026-W41')
    })

    it('ohne Wochen nichts', () => {
        expect(zielwoche([], '2026-W42')).toBeNull()
    })

    it('über den Jahreswechsel: Schlüssel sortieren als Text richtig', () => {
        expect(zielwoche(['2026-W52', '2027-W02'], '2026-W53')).toBe('2027-W02')
    })
})

describe('wochenSchluessel', () => {
    it('passt zu den Schlüsseln der Wochenliste', () => {
        // Mittwoch, 21.10.2026 — Ortszeit, nicht UTC
        const heute = new Date(2026, 9, 21, 23, 30)
        const woche = groupSlotsByWeek([{ id: 'a', date: '2026-10-21', start_period: 1, periods: 1 }], {})
            .find((i) => i.type === 'week')
        expect(wochenSchluessel(heute)).toBe(woche.key)
    })
})

describe('Knopf auf der Planerseite (Quelltext-Wächter)', () => {
    it('ruft die exportierte Sprungfunktion der Tabelle', () => {
        const seite = readFileSync(
            join(SRC, 'routes/(app)/subjects/[slug]/groups/[id]/planner/+page.svelte'), 'utf8')
        expect(seite).toContain('plannerTable?.scrollToCurrentWeek()')
        expect(seite).toContain('Aktuelle Woche')
        const tabelle = readFileSync(join(SRC, 'lib/components/planner/PlannerTable.svelte'), 'utf8')
        expect(tabelle).toContain('export function scrollToCurrentWeek')
    })
})
