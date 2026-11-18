/**
 * Wächter: Die Seitenleisten bestehen aus echten Links (0.48, Päckchen N, F8).
 *
 * Bis 0.47 waren die Einträge `<button>` mit `goto()`. Strg-Klick, Mittelklick und „In
 * neuem Tab öffnen“ gingen nicht, und in aufklappbaren Zeilen reagierten nur Text und
 * Pfeil, nicht der Raum dazwischen (Jan, 03.10.2026).
 *
 * Quelltext statt Verhalten, aus demselben Grund wie in `sidebar_navigation.test.js`.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const KOMPONENTEN = join(dirname(fileURLToPath(import.meta.url)), 'components')
const lies = (name) => readFileSync(join(KOMPONENTEN, name), 'utf8')

describe('Seitenleisten aus Links', () => {
    it.each(['Sidebar.svelte', 'AdminSidebar.svelte'])('%s navigiert nicht per goto', (name) => {
        expect(lies(name)).not.toMatch(/\bgoto\(/)
    })

    it.each(['Sidebar.svelte', 'AdminSidebar.svelte'])('%s nutzt die gemeinsamen Zeilen', (name) => {
        const quelle = lies(name)
        expect(quelle).toContain('<SidebarLink')
        expect(quelle).toContain('<SidebarBereich')
    })

    it('ein Bereich: Link auf ganzer Zeile, Pfeil als eigener Knopf mit Zustand', () => {
        const bereich = lies('SidebarBereich.svelte')
        expect(bereich).toMatch(/<a\s+\{href\}/)
        expect(bereich).toMatch(/<a[^>]*class="flex-1/)
        expect(bereich).toContain('aria-expanded={offen}')
        expect(bereich).toContain('aria-label=')
    })

    it('ein Eintrag ist ein Link und meldet die aktuelle Seite', () => {
        const link = lies('SidebarLink.svelte')
        expect(link).toMatch(/<a\s+\{href\}/)
        expect(link).toContain("aria-current={aktiv ? 'page' : undefined}")
    })

    it('Fächer: Pfeil mit Zustand, Einrückung der Gruppen im Link', () => {
        const fach = lies('SidebarSubjectItem.svelte')
        expect(fach).toContain('aria-expanded={expanded}')
        expect(fach).toMatch(/class="flex items-center gap-2 flex-1 pl-10/)
    })

    it('letzte Chats: das Menü liegt neben dem Link, nicht darin', () => {
        const quelle = lies('Sidebar.svelte')
        const menue = quelle.indexOf('<ConversationMenu')
        expect(menue).toBeGreaterThan(-1)
        const letzterLink = quelle.lastIndexOf('<a', menue)
        const letztesEnde = quelle.lastIndexOf('</a>', menue)
        expect(letztesEnde).toBeGreaterThan(letzterLink)
    })
})
