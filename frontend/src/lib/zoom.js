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

const SVG_NS = 'http://www.w3.org/2000/svg';

/**
 * Den Ausschnitt auf `0 0 Breite Höhe` bringen, ohne dass sich das Bild verändert (0.58.1).
 *
 * Peles Zoom setzt beim Einrichten, Zurücksetzen und bei jeder Größenänderung
 * `viewBox="0 0 width height"` — er nimmt an, dass jede Zeichnung bei 0,0 beginnt und
 * Ausschnitt und Bildgröße denselben Maßstab haben. Für Mermaid und matplotlib stimmt das.
 * CircuiTikZ (node-tikzjax) liefert dagegen etwa `width="76.4" height="109.9"
 * viewBox="-72 -72 57.3 82.4"`: Nach Peles Umschreiben lag die ganze Zeichnung links oberhalb
 * des sichtbaren Bereichs, und **jeder Schaltplan im Chat blieb leer** (seit 0.41).
 *
 * Deshalb wandert der Inhalt in eine Gruppe, die Verschiebung und Maßstab übernimmt; danach
 * passt das SVG zu Peles Annahme. Wirkt auch auf SVGs, die schon im Zwischenspeicher des
 * Backends liegen. Ein zweiter Aufruf ändert nichts mehr.
 */
export function viewBoxAufNull(svg) {
    const box = (svg.getAttribute('viewBox') ?? '').trim().split(/[\s,]+/).map(Number);
    const breite = Number(svg.getAttribute('width'));
    const hoehe = Number(svg.getAttribute('height'));
    if (box.length !== 4 || !box.every(Number.isFinite) || !(box[2] > 0 && box[3] > 0)) return;
    if (!(breite > 0 && hoehe > 0)) return;
    const [x, y, w, h] = box;
    const gleich = (a, b) => Math.abs(a - b) < 1e-6 * Math.max(1, Math.abs(b));
    if (gleich(x, 0) && gleich(y, 0) && gleich(w, breite) && gleich(h, hoehe)) return;

    const gruppe = document.createElementNS(SVG_NS, 'g');
    gruppe.setAttribute('transform', `scale(${breite / w} ${hoehe / h}) translate(${-x} ${-y})`);
    while (svg.firstChild) gruppe.appendChild(svg.firstChild);
    svg.appendChild(gruppe);
    svg.setAttribute('viewBox', `0 0 ${breite} ${hoehe}`);
}

/**
 * Hängt Peles Zoom an `element` (erstes Kind: das SVG). `immer`: Knöpfe auch, wenn das
 * Diagramm schon passt; sonst nur, wenn es verkleinert dargestellt wird.
 */
export async function zoomAnhaengen(element, { immer = false } = {}) {
    const { enableZoom } = await import('pele/lazy');
    const svg = element.firstElementChild;
    if (svg?.localName === 'svg') {
        masseAlsZahl(svg);
        viewBoxAufNull(svg);
    }
    return enableZoom(element, { always: immer, controls: true, labels: ZOOM_LABELS });
}
