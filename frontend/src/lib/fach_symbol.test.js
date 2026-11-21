import { describe, it, expect } from 'vitest'
import { symbolLader } from './fach_symbol.js'

describe('symbolLader', () => {
    it('findet Symbole und Aliasse der Konfiguration', async () => {
        for (const name of ['atom', 'book-open', 'flask-conical', 'code-2', 'square-x']) {
            expect(symbolLader(name), name).toBeTypeOf('function')
        }
    })

    it('unbekannt oder kein Name: null', () => {
        expect(symbolLader('gibt-es-nicht')).toBeNull()
        expect(symbolLader(null)).toBeNull()
        expect(symbolLader('../x')).toBeNull()
    })
})
