import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import {
    ansichtAusEinstellungen, anzahl, archivPfad, datumKurz, einheitenMitOhne, gewaehlteEinheit, klassenKurz,
    menueBeschriftung, menueGruppen, mitBeschriftung, OHNE_EINHEIT, plannerPfad, stundenPfad,
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

describe('Beschriftung im Menü', () => {
    it('Klassen kurz', () => {
        expect(klassenKurz(['10A', '10B', '10C'])).toBe('10A/B/C')
        expect(klassenKurz(['9D', '10A'])).toBe('9D, 10A')
        expect(klassenKurz(['J1'])).toBe('J1')
        expect(klassenKurz([])).toBe('')
    })

    it('Anzeigename, sonst Fach und Klasse, sonst Fach und Jahrgang, sonst Name', () => {
        const g = { name: 'ch-ks-9d', fach: { name: 'Chemie' }, klassen: ['9D'], jahrgang: 9 }
        expect(menueBeschriftung({ ...g, display_name: 'Ch 9d (Mo)' })).toBe('Ch 9d (Mo)')
        expect(menueBeschriftung({ ...g, display_name: '  ' })).toBe('Chemie 9D')
        expect(menueBeschriftung({ ...g, klassen: [] })).toBe('Chemie Kl. 9')
        expect(menueBeschriftung({ ...g, klassen: [], jahrgang: null })).toBe('ch-ks-9d')
    })

    it('gleich Beschriftete bekommen den Namen dazu', () => {
        const fach = { name: 'NwT' }
        const liste = mitBeschriftung([
            { id: 1, name: 'nwt-a', fach, klassen: [], jahrgang: 9 },
            { id: 2, name: 'nwt-b', fach, klassen: [], jahrgang: 9 },
            { id: 3, name: 'nwt-c', fach, klassen: [], jahrgang: 10 },
        ])
        expect(liste.map((g) => g.beschriftung)).toEqual(['NwT Kl. 9 · nwt-a', 'NwT Kl. 9 · nwt-b', 'NwT Kl. 10'])
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
        expect(sidebar).toContain('mitBeschriftung(menueGruppen(')
        expect(sidebar).toContain('{g.beschriftung}')
        expect(sidebar).toMatch(/<SubjectIcon name=\{fach\?\.icon/)
        expect(sidebar).toContain("goto('/planning/archive')")
    })

    it('Stundenentwurf im Lesezustand führt zurück ins Archiv, nicht in den Planer', () => {
        const seite = quelle('routes/(app)/subjects/[slug]/groups/[id]/planner/lessons/[nodeId]/+page.svelte')
        expect(seite).toContain('archivPfad(groupId)')
    })
})
