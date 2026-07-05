// @vitest-environment jsdom
// renderMarkdown + sanitizeSvg nutzen DOMPurify → brauchen im Test ein DOM.
import { describe, it, expect } from 'vitest'
import { renderMarkdown } from './markdown.js'
import { sanitizeSvg } from './serverRender.js'

describe('renderMarkdown: ```circuitikz-Platzhalter', () => {
  it('erzeugt einen circuit-block-Platzhalter statt Code-Highlighting', () => {
    const html = renderMarkdown('```circuitikz\n\\draw (0,0) to[R] (2,0);\n```')
    expect(html).toContain('class="circuit-block"')
    expect(html).not.toContain('code-block') // nicht als Codeblock gehighlightet
  })

  it('escaped die Quelle (kein rohes < > & im Platzhalter)', () => {
    const html = renderMarkdown('```circuitikz\n\\draw (0,0); % a < b & c\n```')
    expect(html).toContain('a &lt; b &amp; c')
    expect(html).not.toContain('a < b & c')
  })

  it('lässt andere Codeblöcke unberührt (kein circuit-block)', () => {
    const html = renderMarkdown('```python\nprint(1)\n```')
    expect(html).toContain('code-block')
    expect(html).not.toContain('circuit-block')
  })

  it('erkennt Tag-Varianten (Groß/Klein, Tippfehler, circuit)', () => {
    for (const tag of ['CircuiTikZ', 'circuittikz', 'circuit', 'Circuit']) {
      const html = renderMarkdown('```' + tag + '\n\\draw (0,0);\n```')
      expect(html, tag).toContain('circuit-block')
      expect(html, tag).not.toContain('code-block')
    }
  })

  it('behandelt latex/tex NICHT als Schaltplan', () => {
    const html = renderMarkdown('```latex\n\\textbf{x}\n```')
    expect(html).not.toContain('circuit-block')
  })
})

describe('sanitizeSvg', () => {
  it('entfernt <script> und Event-Handler, behält die Zeichnung', () => {
    const dirty =
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">' +
      '<script>alert(1)</script>' +
      '<rect x="0" y="0" width="10" height="10" onload="evil()"/>' +
      '<path d="M0 0 L10 10"/>' +
      '</svg>'
    const clean = sanitizeSvg(dirty)
    expect(clean).not.toContain('<script')
    expect(clean).not.toContain('onload')
    expect(clean).not.toContain('alert(1)')
    expect(clean).toContain('<path')
    expect(clean).toContain('<svg')
  })

  it('gibt bei leerem Input leeren String zurück', () => {
    expect(sanitizeSvg('')).toBe('')
  })
})
