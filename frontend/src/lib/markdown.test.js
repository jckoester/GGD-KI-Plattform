// @vitest-environment jsdom
// renderMarkdown nutzt DOMPurify → braucht im Test ein DOM (Produktion: Browser).
import { describe, it, expect } from 'vitest'
import { renderMarkdown } from './markdown.js'

// KaTeX schreibt class="katex" in seine Ausgabe — verlässlicher Marker.
const hasKatex = (html) => html.includes('katex')

describe('renderMarkdown — Markdown-Grundlagen', () => {
    it('leerer Text → ""', () => {
        expect(renderMarkdown('')).toBe('')
    })

    it('rendert Standard-Markdown', () => {
        expect(renderMarkdown('Hallo **Welt**')).toContain('<strong>Welt</strong>')
    })

    it('Text ohne Mathe enthält kein KaTeX', () => {
        expect(hasKatex(renderMarkdown('Nur ganz normaler Text.'))).toBe(false)
    })

    it('entfernt gefährliches HTML weiterhin (Sanitisierung)', () => {
        const html = renderMarkdown('Hallo <script>alert(1)</script> Welt')
        expect(html).not.toContain('<script>')
    })
})

describe('renderMarkdown — Mathe (KaTeX)', () => {
    it('Inline-Mathe $…$ wird gerendert', () => {
        const html = renderMarkdown('Die Formel $E=mc^2$ ist berühmt.')
        expect(hasKatex(html)).toBe(true)
        expect(html).not.toContain('$E=mc^2$')
    })

    it('Block-Mathe $$…$$ wird gerendert (displayMode)', () => {
        const html = renderMarkdown('$$\\int_0^1 x\\,dx$$')
        expect(hasKatex(html)).toBe(true)
        expect(html).toContain('katex-display')
    })

    it('\\(…\\) als Inline-Delimiter (Bildungsplan-Notation)', () => {
        const html = renderMarkdown('Kreiszahl \\(\\pi\\) und \\(\\frac{a}{b}\\).')
        expect(hasKatex(html)).toBe(true)
        expect(html).not.toContain('\\(')
    })

    it('\\[…\\] als Block-Delimiter', () => {
        const html = renderMarkdown('\\[a^2 + b^2 = c^2\\]')
        expect(hasKatex(html)).toBe(true)
        expect(html).toContain('katex-display')
    })

    it('sanitisiert umgebendes Markdown trotz Mathe', () => {
        const html = renderMarkdown('$x$ <script>alert(1)</script>')
        expect(hasKatex(html)).toBe(true)
        expect(html).not.toContain('<script>')
    })
})

describe('renderMarkdown — Chemie (mhchem)', () => {
    // mhchem muss geladen sein, sonst rendert KaTeX \ce/\pu als Fehler (class="katex-error").
    // Die TeX-Quelle (\ce…) steht bewusst in der MathML-<annotation> — das ist korrekt;
    // entscheidend ist die Abwesenheit von katex-error.
    it('rendert eine Reaktionsgleichung \\ce{…} fehlerfrei', () => {
        const html = renderMarkdown('Knallgas: $\\ce{2 H2 + O2 -> 2 H2O}$')
        expect(hasKatex(html)).toBe(true)
        expect(html).not.toContain('katex-error')
    })

    it('rendert \\pu{…} (physikalische Einheit) fehlerfrei', () => {
        const html = renderMarkdown('Energie $\\pu{1.2e3 J//mol}$')
        expect(hasKatex(html)).toBe(true)
        expect(html).not.toContain('katex-error')
    })

    it('Zustände/Pfeile: \\ce{CaCO3 ->[\\Delta] CaO + CO2 ^} fehlerfrei', () => {
        const html = renderMarkdown('$\\ce{CaCO3 ->[\\Delta] CaO + CO2 ^}$')
        expect(hasKatex(html)).toBe(true)
        expect(html).not.toContain('katex-error')
    })
})

describe('renderMarkdown — Code-Kontext bleibt Quelltext', () => {
    it('Inline-Code mit $…$ wird nicht als Mathe gerendert', () => {
        const code = '`' + '$x$' + '`'
        const html = renderMarkdown(code)
        expect(hasKatex(html)).toBe(false)
        expect(html).toContain('<code>$x$</code>')
    })

    it('Bash-Codeblock mit $VAR bleibt unverändert', () => {
        const html = renderMarkdown('```bash\necho $HOME $PATH\n```')
        expect(hasKatex(html)).toBe(false)
        expect(html).toContain('$HOME')
    })
})

describe('renderMarkdown — False-Positive-Disziplin & Robustheit', () => {
    it('Währungsbeträge lösen kein Mathe aus', () => {
        expect(hasKatex(renderMarkdown('Das kostet 5 $ und nochmal 10 $.'))).toBe(false)
    })

    it('$5 und $10 bleiben Text', () => {
        expect(hasKatex(renderMarkdown('Ich habe $5 und du hast $10.'))).toBe(false)
    })

    it('unvollständige Formel (Streaming) wirft nicht und bleibt Text', () => {
        let html
        expect(() => {
            html = renderMarkdown('Gerade tippe ich $x^2 +')
        }).not.toThrow()
        expect(hasKatex(html)).toBe(false)
        expect(html).toContain('$x^2 +')
    })

    it('fehlerhafte TeX in $…$ wirft nicht (throwOnError:false)', () => {
        expect(() => renderMarkdown('$\\frac{1}{$')).not.toThrow()
    })
})
