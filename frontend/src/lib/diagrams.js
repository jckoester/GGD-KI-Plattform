/**
 * Svelte-Action: rendert ```mermaid-Blöcke zu Diagrammen (Phase 15; seit 0.36 mit Pele).
 *
 * `renderMarkdown` erzeugt für jeden Mermaid-Block einen synchronen Platzhalter
 * `<div class="mermaid-block">QUELLE</div>`; diese Action rendert ihn nach dem Mount.
 *
 * **Pele statt Mermaid (0.36).** Pele (`github.com/obsidianmd/pele`, MIT) liest dieselbe
 * Syntax (Mermaid 12.1) und zeichnet mit eigenem Layout; Obsidian nutzt es seit 1.15.0.
 * Gemessen (Plaene/Messungen-Pele): gleiche Parse-Ergebnisse auf 37 Diagrammen, ein Drittel
 * der Größe, unter 10 ms je Diagramm.
 *
 * - **Lazy** (`pele/lazy`): Geladen wird erst beim ersten Block, und nur die Diagrammtypen,
 *   die vorkommen.
 * - **Sanitisiert** wie die Server-Diagramme (`sanitizeSvg`). Bei Mermaid ging das nicht, weil
 *   seine Beschriftungen in `<foreignObject>` steckten; Pele schreibt reines SVG-`<text>`.
 *   Dazu `links: false, images: false`: Ein Diagramm aus dem Chat verlinkt nirgendwohin.
 * - **Farben über CSS-Variablen** (`--pele-*`, gesetzt in `hljs-theme.css` aus den
 *   semantischen Tokens). Der Wechsel hell/dunkel braucht kein neues Rendern.
 * - **Debounce** gegen Streaming-Flackern; erst der vollständige Block wird gerendert.
 * - **Reparatur** vor dem Rendern (`mermaidReparatur.js`): Beschriftungen mit Klammern bekommen
 *   Anführungszeichen. `data-source` behält die Quelle, wie das Modell sie schrieb.
 * - Ungültige Syntax zeigt eine dezente Meldung und die Quelle, statt die Seite zu brechen.
 */
import { sanitizeSvg } from './serverRender.js';
import { mermaidReparieren } from './mermaidReparatur.js';

let _pelePromise = null;
function loadPele() {
    if (!_pelePromise) {
        _pelePromise = import('pele/lazy');
    }
    return _pelePromise;
}

let _seq = 0;

/** Optionen für jedes Diagramm; `idPrefix` hält die IDs mehrerer Diagramme einer Seite auseinander. */
function optionen() {
    return { links: false, images: false, idPrefix: `pele-${_seq++}-` };
}

function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/**
 * Feste Farben für ein Diagramm, das die Seite verlässt (Datei, Bibliothek) — hell, wie auf
 * Papier. Dieselben Werte wie die hellen Tokens in `hljs-theme.css`, nur mit weißem Grund.
 */
export const DATEI_FARBEN = {
    bg: '#ffffff',
    fg: '#100f0f',
    muted: '#575653',
    line: '#100f0f',
    surface: '#f2f0e5',
    'surface-alt': '#e6e4d9',
    border: '#cecdc3',
    accent: '#205ea6',
};

/**
 * Pele-SVG ohne CSS-Variablen.
 *
 * Pele schreibt Farben über zwei Ebenen: `--_fg:var(--pele-fg,#1f1f1f)` im `style` des
 * Wurzelelements, darunter `fill="var(--_fg)"`. Außerhalb der Seite (Word, Inkscape, manche
 * Bildbetrachter) wird `var()` nicht ausgewertet. Erst `--pele-*` durch die Palette ersetzen
 * (sonst den Rückfallwert), dann die internen `--_x`.
 */
export function festeFarben(svg, palette = DATEI_FARBEN) {
    let s = svg.replace(/var\(--pele-([a-z0-9-]+),([^()]*)\)/g, (_, name, rueckfall) =>
        palette[name] ?? rueckfall);
    const intern = Object.fromEntries(
        [...s.matchAll(/--(_[a-z0-9]+):([^;"]+)/g)].map((m) => [m[1], m[2]]));
    for (let i = 0; i < 3; i++) {
        s = s.replace(/var\(--(_[a-z0-9]+)\)/g, (ganz, name) => intern[name] ?? ganz);
    }
    return s.replace(/--_[a-z0-9]+:[^;"]+;?/g, '');
}

/** Das SVG eines Diagramms, sanitisiert — mit Variablen für die Seite. */
export async function diagrammSvg(source) {
    const pele = await loadPele();
    // Klammern in Beschriftungen ohne Anführungszeichen — der häufigste Fehler der Modelle.
    const { svg } = await pele.renderAsync(mermaidReparieren(source), optionen());
    return sanitizeSvg(svg);
}

/** SVG eines Diagramms mit festen, hellen Farben — für Dateien und die Bibliothek. */
export async function mermaidSvgHell(source) {
    return festeFarben(await diagrammSvg(source));
}

export function renderDiagrams(node) {
    let timer = null;

    async function process() {
        if (!node.querySelector('.mermaid-block:not([data-processed])')) return;

        try {
            await loadPele();
        } catch {
            return; // nicht ladbar → Platzhalter (Quelltext) bleibt sichtbar
        }

        for (const block of node.querySelectorAll('.mermaid-block:not([data-processed])')) {
            block.setAttribute('data-processed', ''); // vor await: re-entrante process()-Läufe überspringen
            const source = (block.textContent ?? '').trim();
            if (!source) continue;
            block.dataset.source = source; // Rohquelle für „In Bibliothek speichern" bewahren
            try {
                block.innerHTML = await diagrammSvg(source);
            } catch {
                block.innerHTML =
                    '<div class="mermaid-error">Diagramm konnte nicht dargestellt werden.</div>' +
                    `<pre>${escapeHtml(source)}</pre>`;
            }
        }
    }

    function schedule() {
        clearTimeout(timer);
        timer = setTimeout(process, 250);
    }

    schedule(); // statischer Inhalt: einmal nach kurzem Debounce rendern
    const observer = new MutationObserver(schedule);
    observer.observe(node, { childList: true, subtree: true });

    return {
        destroy() {
            clearTimeout(timer);
            observer.disconnect();
        },
    };
}
