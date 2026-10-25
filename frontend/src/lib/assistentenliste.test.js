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

// Quelltext statt Verhalten — das Projekt mountet keine Svelte-Komponenten.
describe('Wächter: Editor (0.22, C1 Schritt 2)', () => {
    const quelle = lies('lib/components/AssistantEditor.svelte')

    it('Klassenstufen hängen nicht mehr am Scope „Jahrgang“', () => {
        expect(quelle).not.toMatch(/form\.scope === "grade"/)
        expect(quelle).toMatch(/\{#if zeigtKlassenstufen\}/)
        expect(quelle).toMatch(/zeigtKlassenstufen = \$derived\(form\.audience !== "teacher"\)/)
        expect(quelle).toMatch(/zeigtKlassenstufen && form\.min_grade/)
        expect(quelle).toMatch(/zeigtKlassenstufen && form\.max_grade/)
    })

    it('hat ein Feld für visibility und sendet es mit', () => {
        expect(quelle).toMatch(/id="ae-visibility"/)
        expect(quelle).toMatch(/bind:value=\{form\.visibility\}/)
        expect(quelle).toMatch(/visibility: form\.visibility,/)
        expect(quelle).toMatch(/value: "hidden"/)
        // `private` bietet der Editor nicht an; ein Altbestand erscheint als versteckt.
        expect(quelle).not.toMatch(/value: "private",\s*label: "Privat"/)
        expect(quelle).toMatch(/a\.visibility === "public" \? "public" : "hidden"/)
    })

    it('der Scope heißt „Freigabe für“, nicht mehr „Sichtbarkeit“', () => {
        const scopeLabel = quelle.match(/for="ae-scope"[\s\S]*?<\/label>/)[0]
        expect(scopeLabel).toMatch(/Freigabe für/)
        expect(scopeLabel).not.toMatch(/Sichtbarkeit/)
    })
})

describe('Wächter: Link für versteckte Assistenten', () => {
    it('der Editor zeigt ihn, und der Chat nimmt ?assistant_id aus der vollen Liste', () => {
        expect(lies('lib/components/AssistantEditor.svelte')).toMatch(
            /\/chat\?assistant_id=\$\{form\.id\}/,
        )
        expect(lies('routes/(app)/chat/+page.svelte')).toMatch(/paramId && availableAssistants\.length/)
    })
})
