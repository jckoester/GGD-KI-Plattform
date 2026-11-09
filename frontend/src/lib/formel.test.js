import { describe, it, expect } from 'vitest'
import { bereinigeLatex, formelAmCursor, formelEinsetzen } from './formel.js'

describe('formelAmCursor', () => {
    const text = 'Was ist \\(\\frac{1}{2x}\\) für x = 3?'
    const start = text.indexOf('\\(')
    const ende = text.indexOf('\\)') + 2

    it('findet die Formel, in der der Cursor steht', () => {
        expect(formelAmCursor(text, start + 4)).toEqual({ start, ende, tex: '\\frac{1}{2x}', abgesetzt: false })
    })

    it('zählt den Cursor direkt vor und hinter den Begrenzern mit', () => {
        expect(formelAmCursor(text, start)?.tex).toBe('\\frac{1}{2x}')
        expect(formelAmCursor(text, ende)?.tex).toBe('\\frac{1}{2x}')
    })

    it('liefert null außerhalb einer Formel', () => {
        expect(formelAmCursor(text, 3)).toBeNull()
        expect(formelAmCursor(text, text.length)).toBeNull()
        expect(formelAmCursor('', 0)).toBeNull()
    })

    it('kennt auch selbst getipptes TeX: $…$, $$…$$, \\[…\\]', () => {
        expect(formelAmCursor('a $x^2$ b', 4)).toMatchObject({ tex: 'x^2', abgesetzt: false })
        expect(formelAmCursor('$$\\int_0^1 x$$', 5)).toMatchObject({ tex: '\\int_0^1 x', abgesetzt: true })
        expect(formelAmCursor('\\[a+b\\]', 3)).toMatchObject({ tex: 'a+b', abgesetzt: true })
    })

    it('hält Dollar als Währung nicht für eine Formel', () => {
        expect(formelAmCursor('Das kostet 5 $ und 10 $.', 13)).toBeNull()
        expect(formelAmCursor('zwischen $5 und $10', 12)).toBeNull()
    })

    it('nimmt bei mehreren Formeln die richtige', () => {
        const t = '\\(a\\) und \\(b\\)'
        expect(formelAmCursor(t, t.length - 3)?.tex).toBe('b')
    })
})

describe('formelEinsetzen', () => {
    it('setzt an der Cursorstelle ein und stellt den Cursor dahinter', () => {
        const { text, cursor } = formelEinsetzen('Was ist ?', { start: 8, ende: 8 }, 'x^2')
        expect(text).toBe('Was ist \\(x^2\\)?')
        expect(cursor).toBe(15)
    })

    it('ersetzt eine vorhandene Formel samt Begrenzern', () => {
        const t = 'a $x$ b'
        expect(formelEinsetzen(t, formelAmCursor(t, 3), 'x^3').text).toBe('a \\(x^3\\) b')
    })

    it('behält abgesetzte Formeln abgesetzt', () => {
        expect(formelEinsetzen('', { start: 0, ende: 0 }, 'a', true).text).toBe('\\[a\\]')
    })

    it('entfernt die Formel bei leerem Inhalt', () => {
        const t = 'a \\(x\\) b'
        const { text, cursor } = formelEinsetzen(t, formelAmCursor(t, 4), '')
        expect(text).toBe('a  b')
        expect(cursor).toBe(2)
    })
})

describe('bereinigeLatex', () => {
    it('entfernt leere Platzhalter einer unfertigen Formel', () => {
        expect(bereinigeLatex('\\frac{1}{\\placeholder{}}')).toBe('\\frac{1}{}')
        expect(bereinigeLatex('\\sqrt[\\placeholder[index]{}]{2}')).toBe('\\sqrt[]{2}')
    })

    it('ersetzt Befehle der Bildschirmtastatur, die KaTeX nicht kennt', () => {
        expect(bereinigeLatex('f^{\\doubleprime}(x)')).toBe('f^{\\prime\\prime}(x)')
        expect(bereinigeLatex('A\\nsubset B')).toBe('A\\not\\subset B')
        expect(bereinigeLatex('\\ointctrclockwise f')).toBe('\\oint f')
    })

    it('lässt gewöhnliches LaTeX unverändert', () => {
        expect(bereinigeLatex('9{,}81\\cdot\\frac{m}{s^2}')).toBe('9{,}81\\cdot\\frac{m}{s^2}')
        expect(bereinigeLatex('')).toBe('')
        expect(bereinigeLatex(undefined)).toBe('')
    })
})
