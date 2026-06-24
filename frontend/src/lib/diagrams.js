/**
 * Svelte-Action: rendert ```mermaid-Blöcke zu Diagrammen (Phase 15, Schritt 2).
 *
 * `renderMarkdown` erzeugt für jeden Mermaid-Block einen synchronen Platzhalter
 * `<div class="mermaid-block">QUELLE</div>`. Mermaid selbst rendert **asynchron** zu
 * SVG und passt damit nicht in den synchronen renderMarkdown-Pfad (anders als KaTeX) —
 * diese Action übernimmt das Rendern nach dem Mount direkt im DOM.
 *
 * - Mermaid wird **lazy** geladen (dynamischer Import erst beim ersten Block) — die
 *   Bibliothek ist groß und soll das Initial-Bundle nicht belasten.
 * - `securityLevel: 'strict'` — keine Klick-Handler, kein HTML in Labels.
 * - **Debounce** gegen Streaming-Flackern: während Tokens eintrudeln (Chat), wird das
 *   Rendern verschoben; erst wenn der Inhalt zur Ruhe kommt, wird der dann vollständige
 *   Block gerendert. Verhindert Fehl-Render unvollständiger Diagramme.
 * - Render-Fehler (ungültige Syntax) zeigen eine dezente Meldung + die Quelle, statt
 *   die Seite zu brechen.
 */

let _mermaidPromise = null;
function loadMermaid() {
    if (!_mermaidPromise) {
        _mermaidPromise = import('mermaid').then((m) => m.default);
    }
    return _mermaidPromise;
}

let _seq = 0;

function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export function renderDiagrams(node) {
    let timer = null;

    async function process() {
        if (!node.querySelector('.mermaid-block:not([data-processed])')) return;

        let mermaid;
        try {
            mermaid = await loadMermaid();
        } catch {
            return; // Mermaid nicht ladbar → Platzhalter (Quelltext) bleibt sichtbar
        }

        const dark = document.documentElement.classList.contains('dark');
        mermaid.initialize({
            startOnLoad: false,
            securityLevel: 'strict',
            theme: dark ? 'dark' : 'default',
        });

        for (const block of node.querySelectorAll('.mermaid-block:not([data-processed])')) {
            block.setAttribute('data-processed', ''); // vor await: re-entrante process()-Läufe überspringen
            const source = (block.textContent ?? '').trim();
            if (!source) continue;
            try {
                const { svg } = await mermaid.render(`mermaid-svg-${_seq++}`, source);
                block.innerHTML = svg;
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
