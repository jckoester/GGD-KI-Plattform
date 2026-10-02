// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderMarkdown } from './markdown.js'
import {
    diagrammKnoepfe, formelKnopf, formelZumKopieren, svgDatei, texQuelle,
} from './kopieren.js'
import { triggerDownload } from './download.js'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

// Mermaid rendert in jsdom nicht (kein Layout) — die Attrappe gibt die Quelle zurück,
// die sie bekommen hat. So ist prüfbar, mit welchem Thema gerendert wurde.
vi.mock('mermaid', () => ({
    default: {
        initialize: vi.fn(),
        render: vi.fn(async (_id, quelle) => ({ svg: `<svg data-quelle="${quelle}"></svg>` })),
    },
}))
vi.mock('./download.js', () => ({ triggerDownload: vi.fn() }))

const zwischenablage = vi.fn(async () => {})
beforeEach(() => {
    zwischenablage.mockClear()
    vi.mocked(triggerDownload).mockClear()
    Object.defineProperty(navigator, 'clipboard', {
        value: { writeText: zwischenablage }, configurable: true,
    })
})

async function klick(btn) {
    btn.click()
    await new Promise((r) => setTimeout(r, 0))
}

function dom(html) {
    const div = document.createElement('div')
    div.innerHTML = html
    return div
}

describe('kopieren — Formeln', () => {
    it('holt die TeX-Quelle aus der gerenderten Formel', () => {
        const formel = dom(renderMarkdown('$$\\frac{a}{b}$$')).querySelector('.katex-display')
        expect(texQuelle(formel)).toBe('\\frac{a}{b}')
    })

    it('auch Chemie bleibt Quelle, nicht Ergebnis', () => {
        const formel = dom(renderMarkdown('$$\\ce{H2O}$$')).querySelector('.katex-display')
        expect(texQuelle(formel)).toBe('\\ce{H2O}')
    })

    it('kopiert mit $$ — eingefügt wird daraus wieder die Formel', () => {
        const formel = dom(renderMarkdown('$$x^2$$')).querySelector('.katex-display')
        const kopie = formelZumKopieren(formel)
        expect(kopie).toBe('$$x^2$$')
        expect(renderMarkdown(kopie)).toContain('katex-display')
    })

    it('ohne Formel nichts', () => {
        expect(formelZumKopieren(dom('<p>Text</p>'))).toBeNull()
    })
})

describe('kopieren — SVG-Datei', () => {
    it('ergänzt den Namensraum, wenn er fehlt', async () => {
        const text = await svgDatei('<svg width="1"><g/></svg>').text()
        expect(text).toMatch(/^<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg" width="1">/)
    })

    it('lässt einen vorhandenen stehen', async () => {
        const quelle = '<svg xmlns="http://www.w3.org/2000/svg" id="m"><g/></svg>'
        expect(await svgDatei(quelle).text()).toBe(quelle)
    })

    it('ist als SVG ausgewiesen', () => {
        expect(svgDatei('<svg/>').type).toBe('image/svg+xml')
    })
})

describe('kopieren — Knopf an abgesetzten Formeln', () => {
    it('kopiert die Quelle mit $$', async () => {
        const div = dom(renderMarkdown('Text\n\n$$\\ce{2H2 + O2 -> 2H2O}$$'))
        const btn = formelKnopf(div.querySelector('.katex-display'))
        await klick(btn)
        expect(zwischenablage).toHaveBeenCalledWith('$$\\ce{2H2 + O2 -> 2H2O}$$')
    })

    it('sitzt in der Formel und kommt beim Markieren nicht mit', () => {
        const formel = dom(renderMarkdown('$$x$$')).querySelector('.katex-display')
        const btn = formelKnopf(formel)
        expect(btn.parentElement).toBe(formel)
        expect(btn.className).toContain('select-none')
    })

    it('keine Quelle, kein Knopf', () => {
        const leer = dom('<span class="katex-display"></span>').firstElementChild
        expect(formelKnopf(leer)).toBeNull()
        expect(leer.querySelector('button')).toBeNull()
    })
})

describe('kopieren — Leiste an Diagrammen', () => {
    function diagramm(art, quelle, svg = '<svg><g/></svg>') {
        const block = document.createElement('div')
        block.dataset.source = quelle
        block.innerHTML = svg
        const leiste = document.createElement('div')
        diagrammKnoepfe(leiste, block, art, 'k')
        const [code, datei] = leiste.querySelectorAll('button')
        return { code, datei }
    }

    it('„Code kopieren" kopiert die Quelle', async () => {
        const { code } = diagramm('mermaid', 'graph TD; A-->B')
        await klick(code)
        expect(zwischenablage).toHaveBeenCalledWith('graph TD; A-->B')
    })

    it('„SVG" rendert Mermaid im hellen Thema — auch wenn die Seite dunkel ist', async () => {
        document.documentElement.classList.add('dark')
        const { datei } = diagramm('mermaid', 'graph TD; A-->B')
        await klick(datei)
        const [blob, name] = vi.mocked(triggerDownload).mock.calls[0]
        expect(name).toBe('diagramm.svg')
        expect(await blob.text()).toContain('"theme": "default"')
        document.documentElement.classList.remove('dark')
    })

    it('Server-Diagramme gehen, wie sie dastehen', async () => {
        const { datei } = diagramm('circuit', '\\draw (0,0) to[R] (2,0);', '<svg id="schaltung"><g/></svg>')
        await klick(datei)
        const [blob, name] = vi.mocked(triggerDownload).mock.calls[0]
        expect(name).toBe('schaltplan.svg')
        expect(await blob.text()).toContain('id="schaltung"')
    })
})

describe('kopieren — eingebunden', () => {
    // Die Svelte-Seite selbst hat keine Komponententests. Was hier steht, ist das
    // Mindeste: Fiele ein Aufruf weg, bliebe jeder Test oben grün.
    const SRC = dirname(dirname(fileURLToPath(import.meta.url)))

    it('copy-tex ist im Root-Layout geladen — sonst kopiert Markieren Zeichensalat', () => {
        const layout = readFileSync(join(SRC, 'routes', '+layout.svelte'), 'utf8')
        expect(layout).toMatch(/^\s*import 'katex\/contrib\/copy-tex'/m)
    })

    it('der Chat hängt beide Knopfarten an', () => {
        const bubble = readFileSync(join(SRC, 'lib', 'components', 'MessageBubble.svelte'), 'utf8')
        expect(bubble).toContain('formelKnopf(formel)')
        expect(bubble).toContain('diagrammKnoepfe(bar, block, kind, btnClass)')
    })
})
