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

// Platzhalter-Klasse → Backend-Render-„kind".
const BLOCK_KINDS = {
    'circuit-block': 'circuit',
    'plot-block': 'plot',
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
 * Event-Handler, externe/js/data-URIs, behält die Zeichnung. Exportiert für Unit-Tests.
 *
 * `<use>` + `href`/`xlink:href` werden zugelassen — matplotlib rendert Text/Marker als
 * Glyphen-`<use xlink:href="#…">`, node-tikzjax nutzt sie ähnlich. `<script>`, Event-Handler
 * und `javascript:`/`data:`-URIs bleiben blockiert (DOMPurify-Default). Wir setzen bewusst
 * KEINE eigene `ALLOWED_URI_REGEXP` — die würde DOMPurify auch das `d`-Attribut der Pfade
 * prüfen lassen (matcht die Regex nicht → `d` verschwindet → leeres Bild). Externe
 * `<use href="http…">` bleiben damit zwar erlaubt, kommen aus unseren eigenen Renderern aber
 * nie vor (und Browser laden externe `<use>` in Inline-SVG ohnehin nicht).
 */
export function sanitizeSvg(svg) {
    return DOMPurify.sanitize(svg, {
        USE_PROFILES: { svg: true, svgFilters: true },
        ADD_TAGS: ['use'],
        ADD_ATTR: ['xlink:href', 'href'],
    });
}

function renderError(block, source, detail) {
    const msg = detail
        ? `Konnte nicht gerendert werden: ${escapeHtml(detail)}`
        : 'Konnte nicht gerendert werden.';
    block.innerHTML =
        `<div class="server-render-error">${msg}</div>` +
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
        // zeigen wir stattdessen die Quelle + die konkrete Meldung (hilfreicher als das
        // generische Platzhalter-SVG, wie Mermaid).
        if (data.error) { renderError(block, source, data.error); return; }
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
