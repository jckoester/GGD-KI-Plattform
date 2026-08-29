import { describe, it, expect } from 'vitest'
import { zitiername, hatHerkunft, zitatText } from './provenance.js'

describe('zitiername', () => {
    it('streift das LiteLLM-Provider-Präfix ab', () => {
        expect(zitiername('mistral/mistral-small-latest')).toBe('mistral-small-latest')
        expect(zitiername('anthropic/claude-sonnet-5')).toBe('claude-sonnet-5')
    })

    it('kommt mit dem doppelten Präfix bei IONOS zurecht', () => {
        // `openai/` ist hier LiteLLM-Syntax, `openai/` danach der Herausgeber des Modells.
        expect(zitiername('openai/openai/gpt-oss-120b')).toBe('gpt-oss-120b')
        expect(zitiername('openai/black-forest-labs/FLUX.1-schnell')).toBe('FLUX.1-schnell')
    })

    it('lässt präfixlose Namen unverändert', () => {
        expect(zitiername('gpt-4o-mini')).toBe('gpt-4o-mini')
    })

    it('liefert null, wo nichts bekannt ist', () => {
        // null heißt „Herkunft unbekannt", nicht „ohne Modell erzeugt".
        expect(zitiername(null)).toBeNull()
        expect(zitiername(undefined)).toBeNull()
        expect(zitiername('')).toBeNull()
        expect(zitiername('/')).toBeNull()
    })
})

describe('hatHerkunft', () => {
    it('erkennt belegbare und unbekannte Herkunft', () => {
        expect(hatHerkunft({ provider_model: 'mistral/mistral-small-latest' })).toBe(true)
        expect(hatHerkunft({ provider_model: null })).toBe(false)
        expect(hatHerkunft({})).toBe(false)
        expect(hatHerkunft(null)).toBe(false)
    })
})

describe('zitatText', () => {
    const basis = { werkzeug: 'ki@ggd', modell: 'gpt-oss-120b', zeitpunkt: '29.08.2026, 07:31' }

    it('nennt Werkzeug, Modell und Datum', () => {
        expect(zitatText(basis)).toBe('ki@ggd, Modell gpt-oss-120b, abgerufen am 29.08.2026, 07:31')
    })

    it('führt die eigene Eingabe als solche', () => {
        const t = zitatText({ ...basis, eingabe: 'Erkläre mir den Wasserkreislauf' })
        expect(t).toContain('Eigene Eingabe: „Erkläre mir den Wasserkreislauf“')
    })

    it('kennzeichnet den Bild-Prompt als nicht selbst formuliert', () => {
        // Er stammt vom Sprachmodell. Ihn als eigene Eingabe zu zitieren wäre eine
        // Falschangabe — genau das soll der Baustein verhindern.
        const t = zitatText({
            ...basis,
            bilder: [{ modell: 'FLUX.2-klein-4B', prompt: 'Ein roter Würfel' }],
        })
        expect(t).toContain('Bild erzeugt mit FLUX.2-klein-4B')
        expect(t).toContain('vom Sprachmodell formuliert')
        expect(t).not.toContain('Eigene Eingabe: „Ein roter Würfel')
    })

    it('kürzt lange Eingaben, statt die Angabe zu sprengen', () => {
        const t = zitatText({ ...basis, eingabe: 'x'.repeat(500) })
        const zeile = t.split('\n')[1]
        expect(zeile.length).toBeLessThan(340)
        expect(zeile).toContain('…')
    })

    it('normalisiert Zeilenumbrüche in der Eingabe', () => {
        const t = zitatText({ ...basis, eingabe: 'erste Zeile\n\nzweite   Zeile' })
        expect(t).toContain('Eigene Eingabe: „erste Zeile zweite Zeile“')
    })

    it('lässt Unbekanntes weg statt es zu erfinden', () => {
        expect(zitatText({ werkzeug: 'ki@ggd' })).toBe('ki@ggd')
        expect(zitatText({ werkzeug: 'ki@ggd', eingabe: '   ' })).toBe('ki@ggd')
    })
})
