// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { diagrammSvg, festeFarben, mermaidSvgHell, renderDiagrams, DATEI_FARBEN } from './diagrams.js'

const FLUSS = 'flowchart LR\n  A[Eisen] -->|Oxidation| B[Eisenoxid]'

describe('diagrams — Pele (0.36)', () => {
    it('rendert ein Diagramm mit Beschriftung und Farben aus Variablen', async () => {
        const svg = await diagrammSvg(FLUSS)
        expect(svg).toMatch(/^<svg/)
        expect(svg).toContain('Eisenoxid')
        expect(svg).toContain('var(--pele-fg')
    })

    it('kein Link aus dem Diagramm, kein javascript:', async () => {
        const svg = await diagrammSvg('flowchart LR\n  A --> B\n  click A "javascript:alert(1)"\n  click B "https://example.org"')
        expect(svg).not.toContain('javascript:')
        expect(svg).not.toContain('example.org')
    })

    it('ungültige Syntax wirft — die Action zeigt dann Meldung und Quelle', async () => {
        await expect(diagrammSvg('flowchart LR\n  A[Start --> B')).rejects.toThrow()
    })

    it('festeFarben löst beide Ebenen auf (--pele-* und --_x)', () => {
        const roh = '<svg style="--_fg:var(--pele-fg,#1f1f1f);--_bg:var(--pele-bg,#fff);color:var(--_fg)" fill="var(--_fg)"><rect fill="var(--_bg)"/><path stroke="var(--pele-series-3,#123456)"/></svg>'
        const fest = festeFarben(roh)
        expect(fest).not.toContain('var(')
        expect(fest).toContain(`fill="${DATEI_FARBEN.fg}"`)
        expect(fest).toContain(`fill="${DATEI_FARBEN.bg}"`)
        expect(fest).toContain('#123456') // ohne Palettenwert: Rückfall von Pele
    })

    it('mermaidSvgHell: alle Diagrammtypen ohne var()', async () => {
        for (const quelle of [
            FLUSS,
            'mindmap\n  root((Photosynthese))\n    Licht\n    Wasser',
            'pie title Luft\n  "Stickstoff" : 78\n  "Sauerstoff" : 21',
            'sequenceDiagram\n  S->>L: Frage\n  L-->>S: Antwort',
        ]) {
            expect(await mermaidSvgHell(quelle)).not.toContain('var(')
        }
    })

    it('die Action ersetzt den Platzhalter und bewahrt die Quelle', async () => {
        const node = document.createElement('div')
        node.innerHTML = `<div class="mermaid-block">${FLUSS.replace(/>/g, '&gt;')}</div>`
        const action = renderDiagrams(node)
        await new Promise((r) => setTimeout(r, 400))
        const block = node.querySelector('.mermaid-block')
        expect(block.querySelector('svg')).not.toBeNull()
        expect(block.dataset.source).toBe(FLUSS)
        action.destroy()
    })

    it('die Action zeigt bei Fehlern Meldung und Quelle', async () => {
        const node = document.createElement('div')
        node.innerHTML = '<div class="mermaid-block">flowchart LR\n  A[Start --&gt; B</div>'
        const action = renderDiagrams(node)
        await new Promise((r) => setTimeout(r, 400))
        expect(node.querySelector('.mermaid-error')).not.toBeNull()
        expect(node.querySelector('pre').textContent).toContain('A[Start')
        action.destroy()
    })
})
