/**
 * `visibility: hidden` (0.22, Päckchen C1, F3): nicht anzeigen, aber erreichbar lassen.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import { zurAnzeige } from './assistentenliste.js'

const SRC = join(import.meta.dirname, '..')
const lies = (p) => readFileSync(join(SRC, p), 'utf8')

describe('zurAnzeige', () => {
    it('lässt versteckte weg — auch einen Altbestand mit „private“', () => {
        const liste = [{ id: 1, visibility: 'public' }, { id: 2, visibility: 'hidden' },
                       { id: 3, visibility: 'private' }, { id: 4 }]
        expect(zurAnzeige(liste).map((a) => a.id)).toEqual([1, 4])
    })

    it('verträgt fehlende Listen', () => {
        expect(zurAnzeige(undefined)).toEqual([])
    })
})

describe('Anzeige filtert, Einstieg und Direktlink nicht (Quelltext-Wächter)', () => {
    it.each([
        'routes/(app)/assistants/+page.svelte',
        'routes/(app)/tools/+page.svelte',
        'routes/(app)/subjects/[slug]/+page.svelte',
        'lib/components/GruppenUebersicht.svelte',
        'lib/stores/assistants.js',
    ])('%s benutzt zurAnzeige', (datei) => {
        expect(lies(datei)).toContain('zurAnzeige(')
    })

    it('die Auswahl im Chat zeigt die gefilterte Liste', () => {
        const chat = lies('routes/(app)/chat/+page.svelte')
        expect(chat).toContain('assistants={angezeigteAssistenten}')
        // Direktlink (?assistant_id=) und Einstieg suchen in der vollen Liste
        expect(chat).toMatch(/availableAssistants\.find\(/)
        expect(chat).toMatch(/passendeAssistenten\(availableAssistants/)
    })

    it('die Einstiege lesen visibility nicht', () => {
        expect(lies('lib/assistentenwahl.js')).not.toMatch(/zurAnzeige|\.visibility/)
    })
})
