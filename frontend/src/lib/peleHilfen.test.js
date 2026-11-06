import { describe, it, expect } from 'vitest'
import { render } from 'pele'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { mermaidReparieren } from './peleHilfen.js'

const gueltig = (q) => { try { render(q); return true } catch { return false } }

// Echte Modellausgaben (Dev-Chats und Messungen, Plaene/Messungen-Pele/korpus.json), gekürzt.
const KAPUTT = {
    stickstoff_chat: [
        'graph LR',
        '    A[Atmosphärisches N₂] -->|Fixierung (Bakterien, Blitz)<br/>\\(N₂ → NH₄⁺\\)| B[Ammonium (NH₄⁺) im Boden]',
        '    B -->|Nitrifikation (Aerobe Bakterien)| C[Nitrat (NO₃⁻) im Boden / Wasser]',
        '    subgraph Technische Eingriffe',
        '        G[Landwirtschaftliche Düngung] --> B',
        '    end',
        '    style Technische\\ Eingriffe fill:#f9f,stroke:#333,stroke-width:1px',
    ].join('\n'),
    einstieg: 'graph TD\n    A[Motivierender Einstieg (Öl + Wasser)] --> B[Beobachtung & Fragen]',
    sigma: 'graph LR\nA[Ausgang: Benzol + Br₂/FeBr₃] --> B[π‑Komplex]\nB --> C[σ‑Komplex (Arenium‑Ion)]',
    zwei_klammern: 'graph TD\n    A[Trend] --> E[Beispiel: F (oben) > Cl (unten)]',
    kante_strich: 'graph LR\n    A[Valenzband] -- besetzt --> B[Gefülltes Band]\n    B -- Lücke (Verbotene Zone) --> C[Leitungsband (frei)]',
    subgraph_knoten: 'flowchart LR\n    A[N₂ (Luft)] -->|Fixierung| B[NH₄⁺ (Ammonium)]\n    subgraph Bakterien\n        B1[Rhizobien (Leguminosen)]\n    end',
    br_im_label: 'flowchart TD\n    luft[Stickstoff (N₂) in Luft] -->|Fixierung| bact1[Knöllchenbakterien<br>→ NH₄⁺]',
}

describe('mermaidReparieren (0.36)', () => {
    for (const [name, quelle] of Object.entries(KAPUTT)) {
        it(`macht gültig: ${name}`, () => {
            expect(gueltig(quelle)).toBe(false)
            expect(gueltig(mermaidReparieren(quelle))).toBe(true)
        })
    }

    it('setzt Anführungszeichen um Knoten- und Kantentext mit Klammern', () => {
        expect(mermaidReparieren('graph LR\n  A[NO₃⁻ (Nitrat)] -->|Aufnahme (Wurzel)| B[Pflanze]'))
            .toBe('graph LR\n  A["NO₃⁻ (Nitrat)"] -->|"Aufnahme (Wurzel)"| B[Pflanze]')
    })

    it('lässt Gültiges unverändert', () => {
        for (const q of [
            'graph LR\n  A["schon (gequotet)"] --> B[(Datenbank)] --> C[[Unterprogramm]] --> D[/schräg/]',
            'flowchart LR\n  A[Start] --> B{Entscheidung}\n  classDef x fill:#f9d\n  style A fill:#fff',
            'mindmap\n  root((Photosynthese))\n    Licht (Sonne)',
            'sequenceDiagram\n  S->>L: Frage (kurz)',
        ]) {
            expect(mermaidReparieren(q)).toBe(q)
        }
    })

    it('LaTeX am Anfang einer Beschriftung wird repariert, die Trapezform nicht', () => {
        const latex = 'graph LR\n  A[Luft] --> B[\\(N_2\\) (Stickstoff)]'
        expect(gueltig(latex)).toBe(false)
        expect(gueltig(mermaidReparieren(latex))).toBe(true)
        const trapez = 'graph LR\n  A[\\Trapez/] --> B'
        expect(mermaidReparieren(trapez)).toBe(trapez)
    })

    it('Anführungszeichen im Text werden zu #quot;', () => {
        expect(mermaidReparieren('graph LR\n  A[Er sagt "hallo" (laut)] --> B'))
            .toContain('A["Er sagt #quot;hallo#quot; (laut)"]')
    })
})

describe('peleHilfen — Kopie im Render-Sidecar', () => {
    it('render-sidecar/peleHilfen.mjs ist wortgleich', () => {
        const hier = dirname(fileURLToPath(import.meta.url))
        const original = readFileSync(join(hier, 'peleHilfen.js'), 'utf8')
        const kopie = readFileSync(join(hier, '../../../render-sidecar/peleHilfen.mjs'), 'utf8')
        expect(kopie).toBe(original)
    })
})
