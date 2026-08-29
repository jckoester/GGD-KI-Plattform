import { describe, it, expect } from 'vitest'
import { zitiername, hatHerkunft } from './provenance.js'

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
