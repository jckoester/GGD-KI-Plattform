/**
 * Zoom für Diagramme (0.41, Schritt 8) — eine Stelle für Produktansicht und Chat.
 *
 * Pele (`enableZoom`) arbeitet mit dem SVG, das erstes Kind des Elements ist, und liest
 * dessen natürliche Größe aus `width`/`height` als **Zahl**. matplotlib schreibt aber
 * `width="216pt"` — dann hält Pele die Größe für 0 und zeigt nie Knöpfe. `masseAlsZahl`
 * rechnet solche Angaben vorher in Pixel um.
 */

export const ZOOM_LABELS = { zoomIn: 'Vergrößern', zoomOut: 'Verkleinern', reset: 'Zurücksetzen' };

const PX_JE_EINHEIT = { px: 1, pt: 4 / 3, pc: 16, in: 96, cm: 96 / 2.54, mm: 96 / 25.4 };

function inPixel(wert) {
    const m = /^\s*([\d.]+)\s*([a-z]*)\s*$/i.exec(wert ?? '');
    if (!m) return null;
    const faktor = PX_JE_EINHEIT[m[2].toLowerCase() || 'px'];
    return faktor ? Number(m[1]) * faktor : null;
}

/** `width`/`height` des SVG als reine Zahl (px); ohne brauchbare Angabe aus der viewBox. */
export function masseAlsZahl(svg) {
    const box = (svg.getAttribute('viewBox') ?? '').trim().split(/[\s,]+/).map(Number);
    const ausBox = box.length === 4 && box.every(Number.isFinite) ? { width: box[2], height: box[3] } : null;
    for (const seite of ['width', 'height']) {
        const roh = svg.getAttribute(seite);
        if (roh !== null && /^\s*[\d.]+\s*$/.test(roh)) continue;
        const px = inPixel(roh) ?? ausBox?.[seite];
        if (px) svg.setAttribute(seite, String(Math.round(px * 100) / 100));
    }
}

/**
 * Hängt Peles Zoom an `element` (erstes Kind: das SVG). `immer`: Knöpfe auch, wenn das
 * Diagramm schon passt; sonst nur, wenn es verkleinert dargestellt wird.
 */
export async function zoomAnhaengen(element, { immer = false } = {}) {
    const { enableZoom } = await import('pele/lazy');
    const svg = element.firstElementChild;
    if (svg?.localName === 'svg') masseAlsZahl(svg);
    return enableZoom(element, { always: immer, controls: true, labels: ZOOM_LABELS });
}
