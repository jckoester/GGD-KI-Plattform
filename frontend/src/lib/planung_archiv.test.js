import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import {
    ansichtAusEinstellungen, anzahl, archivPfad, datumKurz, einheitenMitOhne, gewaehlteEinheit,
    menueGruppen, OHNE_EINHEIT, plannerPfad, stundenPfad,
} from './planung_archiv.js'

const SRC = join(__dirname, '..')
const quelle = (pfad) => readFileSync(join(SRC, pfad), 'utf8')

const chemie = { slug: 'chemie', name: 'Chemie' }
const bio = { slug: 'biologie', name: 'Biologie' }

describe('menueGruppen', () => {
    it('nur aktuelle Gruppen mit Fach, nach Fach und Name', () => {
        const gruppen = [
            { id: 1, name: 'Ch 9b', fach: chemie, aktuell: true },
            { id: 2, name: 'Ch 9a', fach: chemie, aktuell: true },
            { id: 3, name: 'Bio 7', fach: bio, aktuell: true },
            { id: 4, name: 'Ch alt', fach: chemie, aktuell: false },
            { id: 5, name: 'Ohne Fach', fach: null, aktuell: true },
            { id: 6, name: 'Ch ohne Feld', fach: chemie },
        ]
        expect(menueGruppen(gruppen).map((g) => g.id)).toEqual([3, 2, 1, 6])
    })

    it('leer bleibt leer', () => {
        expect(menueGruppen(undefined)).toEqual([])
    })
})

describe('Pfade', () => {
    it('Planer, Archiv, Einheit und Stunde', () => {
        const g = { id: 7, fach: chemie }
        expect(plannerPfad(g)).toBe('/subjects/chemie/groups/7/planner')
        expect(archivPfad()).toBe('/planning/archive')
        expect(archivPfad(7)).toBe('/planning/archive/7')
        expect(archivPfad(7, OHNE_EINHEIT)).toBe('/planning/archive/7?einheit=ohne')
        expect(stundenPfad(g, 'abc')).toBe('/subjects/chemie/groups/7/planner/lessons/abc')
    })
})

describe('Einheiten im Archiv', () => {
    const inhalt = {
        einheiten: [{ id: 'u1', titel: 'Säuren', stunden: [{ id: 's1' }] }],
        ohne_einheit: [{ id: 's2' }],
    }

    it('„Stunden ohne Einheit“ als letzte Kachel, nur wenn es welche gibt', () => {
        expect(einheitenMitOhne(inhalt).map((e) => e.schluessel)).toEqual(['u1', OHNE_EINHEIT])
        expect(einheitenMitOhne({ ...inhalt, ohne_einheit: [] }).map((e) => e.schluessel)).toEqual(['u1'])
    })

    it('Auswahl über die Adresse', () => {
        expect(gewaehlteEinheit(inhalt, 'u1').titel).toBe('Säuren')
        expect(gewaehlteEinheit(inhalt, OHNE_EINHEIT).stunden).toEqual([{ id: 's2' }])
        expect(gewaehlteEinheit(inhalt, 'gibts-nicht')).toBeNull()
        expect(gewaehlteEinheit(inhalt, null)).toBeNull()
    })
})

describe('Kleinkram', () => {
    it('Ansicht: gemerkt oder Kacheln', () => {
        expect(ansichtAusEinstellungen({ planung_archiv_ansicht: 'liste' })).toBe('liste')
        expect(ansichtAusEinstellungen({ planung_archiv_ansicht: 'quatsch' })).toBe('kacheln')
        expect(ansichtAusEinstellungen(null)).toBe('kacheln')
    })

    it('Anzahl und Datum', () => {
        expect(anzahl(1, 'Stunde', 'Stunden')).toBe('1 Stunde')
        expect(anzahl(0, 'Stunde', 'Stunden')).toBe('0 Stunden')
        expect(datumKurz('2026-09-14')).toBe('14.09.2026')
        expect(datumKurz(null)).toBe('')
    })
})

describe('Verdrahtung', () => {
    it('Menüpunkt „Planung“ mit Gruppen und Archiv, Stufen-Schlüssel planner', () => {
        const sidebar = quelle('lib/components/Sidebar.svelte')
        expect(sidebar).toMatch(/\$zeigtEintrag\('planner'\)/)
        expect(sidebar).toContain('menueGruppen(')
        expect(sidebar).toContain("goto('/planning/archive')")
    })

    it('Stundenentwurf im Lesezustand führt zurück ins Archiv, nicht in den Planer', () => {
        const seite = quelle('routes/(app)/subjects/[slug]/groups/[id]/planner/lessons/[nodeId]/+page.svelte')
        expect(seite).toContain('archivPfad(groupId)')
    })
})
