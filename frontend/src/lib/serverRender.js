/**
 * Svelte-Action: rendert server-gerenderte Blöcke (Phase 17) zu SVG.
 *
 * Spiegelt das Mermaid-Muster (diagrams.js), aber statt einer Client-Bibliothek wird
 * das SVG **vom Backend** geholt (POST /render/{kind}). Eine **generische** Action für
 * alle server-gerenderten Block-Typen (Schritt 3: CircuiTikZ; Schritt 6: Plots).
 *
 * `renderMarkdown` erzeugt für jeden Block einen synchronen Platzhalter
 * `<div class="circuit-block">QUELLE</div>` (Quelle escaped als textContent). Diese
 * Action liest die Quelle nach dem Mount, holt das gecachte SVG und injiziert es —
 * **DOMPurify-sanitisiert** (Plan-Invariante: die Sicherheitsgrenze bleibt strikt).
 *
 * - Debounce (250 ms) + MutationObserver gegen Streaming-Flackern (wie Mermaid).
 * - Ladezustand während des Fetch; Fehler zeigen eine dezente Meldung + die Quelle.
 */
import DOMPurify from 'dompurify';

const BASE = '/api';

// Platzhalter-Klasse → Backend-Render-„kind". Schritt 6 ergänzt 'plot-block': 'plot'.
const BLOCK_KINDS = {
    'circuit-block': 'circuit',
};

const SELECTOR = Object.keys(BLOCK_KINDS)
    .map((cls) => `.${cls}:not([data-processed])`)
    .join(', ');

function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/**
 * Sanitisiert ein server-geliefertes SVG. Die Quelle ist vertrauenswürdig (eigenes
 * Backend/Sidecar), wird aber dennoch strikt sanitisiert — entfernt <script>,
 * Event-Handler und Fremd-Markup, behält die Zeichnung. Exportiert für Unit-Tests.
 */
export function sanitizeSvg(svg) {
    return DOMPurify.sanitize(svg, { USE_PROFILES: { svg: true, svgFilters: true } });
}

function renderError(block, source) {
    block.innerHTML =
        '<div class="server-render-error">Konnte nicht gerendert werden.</div>' +
        `<pre>${escapeHtml(source)}</pre>`;
}

async function renderBlock(block, kind) {
    const source = (block.textContent ?? '').trim();
    block.setAttribute('data-processed', ''); // vor await: re-entrante Läufe überspringen
    if (!source) return;
    block.innerHTML = '<div class="server-render-loading">Wird gerendert…</div>';
    try {
        const res = await fetch(`${BASE}/render/${kind}`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source }),
        });
        if (!res.ok) throw new Error(`render http ${res.status}`);
        const data = await res.json();
        // Backend liefert bei Render-Fehlern ein Platzhalter-SVG + `error` — im Chat
        // zeigen wir stattdessen die Quelle (hilfreicher für Autor:innen, wie Mermaid).
        if (data.error) { renderError(block, source); return; }
        block.innerHTML = sanitizeSvg(data.svg ?? '');
    } catch {
        renderError(block, source);
    }
}

export function renderServerBlocks(node) {
    let timer = null;

    async function process() {
        const blocks = node.querySelectorAll(SELECTOR);
        for (const block of blocks) {
            const cls = Object.keys(BLOCK_KINDS).find((c) => block.classList.contains(c));
            const kind = cls && BLOCK_KINDS[cls];
            if (!kind) { block.setAttribute('data-processed', ''); continue; }
            await renderBlock(block, kind);
        }
    }

    function schedule() {
        clearTimeout(timer);
        timer = setTimeout(process, 250);
    }

    schedule();
    const observer = new MutationObserver(schedule);
    observer.observe(node, { childList: true, subtree: true });

    return {
        destroy() {
            clearTimeout(timer);
            observer.disconnect();
        },
    };
}
