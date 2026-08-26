// @vitest-environment jsdom
// renderMarkdown nutzt DOMPurify → braucht im Test ein DOM (Produktion: Browser).
import { describe, it, expect } from 'vitest'
import { renderInlineMath, renderMarkdown } from './markdown.js'

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

describe('renderMarkdown — URL-Allowlist (Audit #16)', () => {
    it('javascript:-Link wird entschärft', () => {
        const html = renderMarkdown('[klick](javascript:alert(1))')
        expect(html).not.toContain('javascript:')
    })

    it('data:text/html in einem Link wird blockiert', () => {
        // <a href="data:…"> ist ein Vektor (Top-Level-Navigation) → von der Allowlist erfasst.
        // (data: auf <img> ist DOMPurify-Default und kein XSS-Vektor, daher hier nicht geprüft.)
        const html = renderMarkdown('[x](data:text/html;base64,PHNjcmlwdD4=)')
        expect(html).not.toContain('data:text/html')
    })

    it('vbscript:-Link wird blockiert', () => {
        const html = renderMarkdown('[x](vbscript:msgbox(1))')
        expect(html).not.toContain('vbscript:')
    })

    it('https-Link bleibt erhalten', () => {
        const html = renderMarkdown('[GGD](https://example.de/seite)')
        expect(html).toContain('href="https://example.de/seite"')
    })

    it('mailto-Link bleibt erhalten', () => {
        const html = renderMarkdown('[Mail](mailto:info@example.de)')
        expect(html).toContain('href="mailto:info@example.de"')
    })

    it('relativer Pfad bleibt erhalten', () => {
        const html = renderMarkdown('[Hilfe](/help/chat)')
        expect(html).toContain('href="/help/chat"')
    })

    it('Anchor-Link (#) bleibt erhalten', () => {
        const html = renderMarkdown('[Abschnitt](#ziele)')
        expect(html).toContain('href="#ziele"')
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

describe('renderMarkdown — Mermaid-Platzhalter', () => {
    it('```mermaid wird zu einem .mermaid-block-Platzhalter (nicht hervorgehoben)', () => {
        const html = renderMarkdown('```mermaid\ngraph TD\n A --> B\n```')
        expect(html).toContain('mermaid-block')
        expect(html).not.toContain('hljs') // kein Syntax-Highlighting für Mermaid
        expect(html).toContain('graph TD') // Quelle bleibt als Textinhalt erhalten
    })

    it('normale Codeblöcke werden weiterhin hervorgehoben (Regression)', () => {
        const html = renderMarkdown('```python\nprint("hi")\n```')
        expect(html).toContain('hljs')
        expect(html).not.toContain('mermaid-block')
    })

    it('Mermaid-Block überlebt die Sanitisierung', () => {
        const html = renderMarkdown('```mermaid\nflowchart LR\n X-->Y\n```')
        expect(html).toContain('class="mermaid-block"')
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

describe('renderInlineMath — Formeln in Titeln', () => {
    // Bildungsplan-Kompetenzen tragen ihre Formeln im Titel; Titel stehen in Bäumen und
    // Listen, wo Markdown-Blockstruktur nichts zu suchen hat.
    const BP_TITEL = '3.1.2(10) die Zahl \\(\\pi\\) als Verhältnis von Umfang erklären'

    it('rendert \\(…\\) aus einem echten Bildungsplan-Titel', () => {
        expect(hasKatex(renderInlineMath(BP_TITEL))).toBe(true)
    })

    it('erzeugt keinen Absatz — anders als renderMarkdown', () => {
        expect(renderInlineMath(BP_TITEL)).not.toContain('<p>')
        expect(renderMarkdown(BP_TITEL)).toContain('<p>')
    })

    it('lässt Markdown-Zeichen Text bleiben', () => {
        // Ein Titel wie „Wachstum a_1 * q^n" darf nicht kursiv werden.
        const html = renderInlineMath('Der Wert _n_ und *m* bleiben Text')
        expect(html).not.toContain('<em>')
        expect(html).toContain('_n_')
    })

    it('escapet HTML im umgebenden Text', () => {
        const html = renderInlineMath('<script>alert(1)</script> und \\(x\\)')
        expect(html).not.toContain('<script>')
        expect(html).toContain('&lt;script&gt;')
        expect(hasKatex(html)).toBe(true)
    })

    it('escapet auch, wenn gar keine Formel vorkommt', () => {
        expect(renderInlineMath('a < b & c')).toBe('a &lt; b &amp; c')
    })

    it('rendert mehrere Formeln in einem Titel', () => {
        const html = renderInlineMath('\\(a^2\\) plus \\(b^2\\)')
        expect(html.match(/class="katex"/g)?.length).toBe(2)
        expect(html).toContain('plus')
    })

    it('beherrscht auch $…$', () => {
        expect(hasKatex(renderInlineMath('Formel $x^2$ hier'))).toBe(true)
    })

    it('lässt ein einzelnes Dollarzeichen in Ruhe', () => {
        const html = renderInlineMath('Das kostet 5 $ pro Stück')
        expect(hasKatex(html)).toBe(false)
        expect(html).toContain('5 $ pro')
    })

    it('leerer Text → ""', () => {
        expect(renderInlineMath('')).toBe('')
        expect(renderInlineMath(null)).toBe('')
        expect(renderInlineMath(undefined)).toBe('')
    })

    it('kaputte Formel zerstört den Titel nicht', () => {
        const html = renderInlineMath('Anfang \\(\\frac{1 offen und Text danach')
        expect(html).toContain('Anfang')
        expect(html).toContain('Text danach')
    })
})

describe('renderInlineMath — echte Bildungsplan-Titel', () => {
    // Wörtlich aus der Datenbank; sie decken die Makros ab, die im BP tatsächlich
    // vorkommen (\frac, \cdot, \mathrm, Hoch-/Tiefstellung, mehrere Formeln je Titel).
    const ECHT = [
        '3.6.2.1(6) die Kapazität eines Kondensators erläutern ( \\(C = \\frac{Q}{U}\\) )',
        '3.2.2(6) die Lageenergie berechnen ( \\(E_\\mathrm{Lage} = m \\cdot g \\cdot h\\) , Nullniveau)',
        '3.4.4(3) charakteristische Eigenschaften der Funktion \\(f\\) mit \\(f(x)=e^{x}\\) beschreiben',
        '3.3.3(4) die Beziehungen \\(sin^2(\\alpha) + cos^2(\\alpha) = 1\\) , \\(sin(90° - \\alpha) = cos(\\alpha)\\)',
    ]

    it.each(ECHT)('rendert: %s', (titel) => {
        const html = renderInlineMath(titel)
        expect(hasKatex(html)).toBe(true)
        // Die Quell-Notation darf nicht mehr sichtbar sein …
        expect(html).not.toContain('\\(')
        // … und der umgebende Text bleibt erhalten.
        expect(html).toContain(titel.slice(0, 10))
    })

    it('rendert jede Formel eines Titels einzeln', () => {
        const html = renderInlineMath(ECHT[3])
        expect(html.match(/class="katex"/g)?.length).toBe(2)
    })
})
