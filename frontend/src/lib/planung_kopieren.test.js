import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import {
    einheitenPfad, ergebnisPfad, kopierAnfrage, meldungenZusammenfassung, meldungText, NEUE_EINHEIT, zielGruppen,
} from './planung_kopieren.js'

const SRC = join(__dirname, '..')
const quelle = (pfad) => readFileSync(join(SRC, pfad), 'utf8')

const chemie = { id: 1, slug: 'chemie', name: 'Chemie' }
const physik = { id: 2, slug: 'physik', name: 'Physik' }

describe('zielGruppen', () => {
    it('nur aktuelle Gruppen desselben Fachs', () => {
        const gruppen = [
            { id: 10, name: 'Ch 9b', fach: chemie, aktuell: true },
            { id: 11, name: 'Ch 9a', fach: chemie, aktuell: true },
            { id: 12, name: 'Ph 9', fach: physik, aktuell: true },
            { id: 13, name: 'Ch alt', fach: chemie, aktuell: false },
            { id: 14, name: 'Ohne Fach', fach: null, aktuell: true },
        ]
        expect(zielGruppen(gruppen, 1).map((g) => g.id)).toEqual([11, 10])
        expect(zielGruppen(gruppen, null)).toEqual([])
    })
})

describe('kopierAnfrage', () => {
    it('Einheit braucht nur die Gruppe', () => {
        expect(kopierAnfrage('einheit', { gruppeId: 10 })).toEqual({ gruppe_id: 10 })
        expect(kopierAnfrage('einheit', { gruppeId: null })).toBeNull()
    })

    it('Stunde braucht genau eins: Einheit oder Titel einer neuen', () => {
        expect(kopierAnfrage('stunde', { gruppeId: 10, einheitWahl: 'u1' })).toEqual({ gruppe_id: 10, einheit_id: 'u1' })
        expect(kopierAnfrage('stunde', { gruppeId: 10, einheitWahl: NEUE_EINHEIT, neuerTitel: '  Redox ' }))
            .toEqual({ gruppe_id: 10, neue_einheit: 'Redox' })
        expect(kopierAnfrage('stunde', { gruppeId: 10, einheitWahl: NEUE_EINHEIT, neuerTitel: '  ' })).toBeNull()
        expect(kopierAnfrage('stunde', { gruppeId: 10, einheitWahl: '' })).toBeNull()
    })
})

describe('Ergebnis', () => {
    const gruppe = { id: 10, fach: chemie }

    it('Link zur Kopie bzw. zum Planer', () => {
        expect(ergebnisPfad('stunde', { id: 's9' }, gruppe)).toBe('/subjects/chemie/groups/10/planner/lessons/s9')
        expect(ergebnisPfad('einheit', { id: 'u9' }, gruppe))
            .toBe('/subjects/chemie/groups/10/planner?ansicht=einheiten&einheit=u9')
        expect(ergebnisPfad('stunde', null, gruppe)).toBeNull()
    })

    it('die Kopie hat keinen Termin: Weg in die Einheitenansicht (0.42.3)', () => {
        expect(einheitenPfad('stunde', { id: 's9', einheit_id: 'u3' }, gruppe))
            .toBe('/subjects/chemie/groups/10/planner?ansicht=einheiten&einheit=u3')
        expect(einheitenPfad('einheit', { id: 'u9' }, gruppe))
            .toBe('/subjects/chemie/groups/10/planner?ansicht=einheiten&einheit=u9')
        expect(einheitenPfad('stunde', null, gruppe)).toBeNull()
    })

    it('Meldungen lesbar', () => {
        const m = [
            { art: 'material', titel: 'AB 1', was: 'weggelassen', grund: 'Für die Gruppe nicht freigegeben.', phase: 'Einstieg', stunde: 'Eins' },
            { art: 'kompetenz', titel: '3.2.1(1)', was: 'umgestellt', grund: 'Auf die Fassung umgestellt.' },
        ]
        expect(meldungText(m[0])).toBe('Material „AB 1“ (Eins, Einstieg) nicht übernommen: Für die Gruppe nicht freigegeben.')
        expect(meldungText(m[1])).toBe('Kompetenz „3.2.1(1)“ umgestellt: Auf die Fassung umgestellt.')
        expect(meldungenZusammenfassung(m)).toBe('1 Verweis nicht übernommen, 1 auf die Fassung der Gruppe umgestellt')
        expect(meldungenZusammenfassung([])).toBe('')
    })
})

describe('Verdrahtung (Einstiege, Plan Vorschlag 5)', () => {
    it('Archiv: Einheiten und Stunden', () => {
        const seite = quelle('routes/(app)/planning/archive/[id]/+page.svelte')
        expect(seite).toContain('<KopierenDialog')
        expect(seite).toContain('onKopiereEinheit={kopiereEinheit}')
        expect(seite).toContain('onKopiereStunde={kopiereStunde}')
        // Die Knöpfe selbst stehen in der gemeinsamen Darstellung (0.42.3).
        const ansicht = quelle('lib/components/planner/EinheitenAnsicht.svelte')
        expect(ansicht).toContain('onKopiereEinheit(e)')
        expect(ansicht).toContain('onKopiereStunde(s, einheit)')
    })

    it('Einheitenansicht des Planers (0.42.3): Einheiten und Stunden', () => {
        const seite = quelle('routes/(app)/subjects/[slug]/groups/[id]/planner/+page.svelte')
        expect(seite).toMatch(/onKopiereEinheit=\{\(e\) => \(kopieren = \{ art: 'einheit'/)
        expect(seite).toMatch(/onKopiereStunde=\{\(st, e\) => \(kopieren = \{\s*art: 'stunde'/)
    })

    it('Jahresübersicht an der Einheit', () => {
        expect(quelle('routes/(app)/subjects/[slug]/groups/[id]/planner/+page.svelte')).toMatch(/onCopyUnit=/)
        expect(quelle('lib/components/planner/UnitLegend.svelte')).toContain('onCopyUnit(unit)')
    })

    it('Stundenentwurf: Kopieren auch im Lesezustand, Notiz aus der Vorlage', () => {
        const seite = quelle('routes/(app)/subjects/[slug]/groups/[id]/planner/lessons/[nodeId]/+page.svelte')
        expect(seite).toContain('art="stunde"')
        expect(seite).toContain('notiz_aus_vorlage_entfernen: true')
        expect(seite).toContain('Notiz aus der Vorlage')
    })
})
