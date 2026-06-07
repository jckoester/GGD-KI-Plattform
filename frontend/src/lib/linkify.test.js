import { describe, it, expect } from 'vitest'
import { linkifyText } from './linkify.js'

describe('linkifyText', () => {
    it('leerer Text → []', () => {
        expect(linkifyText('')).toEqual([])
    })

    it('reiner Text ohne URL → ein text-Part', () => {
        expect(linkifyText('nur text')).toEqual([{ kind: 'text', label: 'nur text' }])
    })

    it('erkennt eine URL zwischen Text', () => {
        const parts = linkifyText('siehe https://example.com hier')
        expect(parts).toEqual([
            { kind: 'text', label: 'siehe ' },
            { kind: 'url', label: 'https://example.com', href: 'https://example.com' },
            { kind: 'text', label: ' hier' },
        ])
    })

    it('nachgestellte Satzzeichen gehören nicht zur URL', () => {
        const parts = linkifyText('siehe https://example.com.')
        expect(parts).toEqual([
            { kind: 'text', label: 'siehe ' },
            { kind: 'url', label: 'https://example.com', href: 'https://example.com' },
            { kind: 'text', label: '.' },
        ])
    })

    it('Klammern bleiben Teil der URL (z. B. Wikipedia)', () => {
        const url = 'https://de.wikipedia.org/wiki/Funktion_(Mathematik)'
        const parts = linkifyText(url)
        expect(parts).toEqual([{ kind: 'url', label: url, href: url }])
    })

    it('mehrere URLs', () => {
        const parts = linkifyText('a https://x.de b https://y.de')
        expect(parts.filter((p) => p.kind === 'url').map((p) => p.href)).toEqual([
            'https://x.de',
            'https://y.de',
        ])
    })
})
