/**
 * Kopieren und Sichern an gerenderten Formeln und Diagrammen (0.12, AP6c).
 *
 * Codeblöcke hatten ihren „Kopieren"-Knopf, gerenderte Formeln und Diagramme nicht: Sie
 * zeigten nur das Ergebnis, die Quelle war weg. Sie ist es nicht — KaTeX bettet sie bei
 * `output: 'htmlAndMathml'` als MathML-Annotation ein, und `diagrams.js` bzw.
 * `serverRender.js` legen die Diagrammquelle in `data-source` ab. Hier wird sie nur
 * herausgeholt.
 */
import { mermaidSvgHell } from './diagrams.js';
import { triggerDownload } from './download.js';

/** TeX-Quelle einer gerenderten Formel — oder ``null``, wenn es keine gibt. */
export function texQuelle(element) {
    return element?.querySelector('annotation[encoding="application/x-tex"]')?.textContent ?? null;
}

/**
 * Was der Knopf an einer abgesetzten Formel kopiert: ``$$…$$``.
 *
 * Dieselbe Schreibweise, die `katex/contrib/copy-tex` beim Markieren liefert — Knopf
 * und Markieren sollen nicht zwei verschiedene Ergebnisse haben. Eingefügt in Chat,
 * Werkstatt oder Wissensknoten wird daraus wieder die Formel.
 */
export function formelZumKopieren(katexDisplay) {
    const tex = texQuelle(katexDisplay);
    return tex == null ? null : `$$${tex}$$`;
}

/** Dateiname beim Sichern als SVG, je Diagrammart. */
export const SVG_DATEINAME = {
    mermaid: 'diagramm.svg',
    circuit: 'schaltplan.svg',
    plot: 'funktionsgraph.svg',
};

/**
 * Das SVG, das „In Bibliothek speichern" mitschickt — nur Mermaid braucht eins.
 *
 * Schaltplan und Funktionsgraph rendert der Server aus der Quelle neu; Mermaid kann er
 * nicht, er übernimmt das SVG des Browsers. Bis 0.12 war das das **angezeigte** — im
 * Dunkelmodus also helle Linien auf durchsichtigem Grund, in der Bibliothek und als PNG
 * kaum lesbar. Jetzt dieselbe helle Fassung wie beim Download.
 *
 * ⚠️ Ein schon gespeichertes Diagramm wird dadurch nicht hell: Die Bibliothek erkennt
 * es an seiner Quelle wieder und gibt das vorhandene zurück.
 */
export async function bibliotheksSvg(art, quelle) {
    return art === 'mermaid' ? mermaidSvgHell(quelle) : null;
}

/** Ein SVG-Element als eigenständige Datei (mit Namensraum, sonst zeigt kein Programm es an). */
export function svgDatei(svgText) {
    const text = /\sxmlns=/.test(svgText.slice(0, svgText.indexOf('>')))
        ? svgText
        : svgText.replace(/^<svg\b/, '<svg xmlns="http://www.w3.org/2000/svg"');
    return new Blob([text], { type: 'image/svg+xml' });
}

// ── Die Knöpfe ──────────────────────────────────────────────────────────────
// Hier und nicht in der Svelte-Action von `MessageBubble`: Dort ließe sich nicht prüfen,
// ob ein Klick tatsächlich das Richtige kopiert — eine Gegenprobe bliebe grün.

const FORMEL_KNOPF = [
    'absolute top-0 right-0 select-none',
    'px-1.5 py-0.5 rounded text-xs',
    'bg-light-ui-2 dark:bg-dark-ui-2',
    'text-light-tx-2 dark:text-dark-tx-2',
    'hover:bg-light-ui-3 dark:hover:bg-dark-ui-3',
    'opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity',
].join(' ');

/**
 * Hängt an eine abgesetzte Formel (`.katex-display`) den Knopf „Kopieren".
 *
 * Nur abgesetzte Formeln: Ein Knopf je Formel im Fließtext wäre überladen, und dort
 * liefert Markieren und Kopieren dank `katex/contrib/copy-tex` ohnehin die Quelle.
 * `select-none`, damit das Wort „Kopieren" beim Markieren nicht mitkommt.
 *
 * @returns {HTMLButtonElement|null} ``null``, wenn die Formel keine Quelle trägt
 */
export function formelKnopf(formel) {
    if (!formelZumKopieren(formel)) return null;
    formel.classList.add('relative', 'group');

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.setAttribute('aria-label', 'Formel als LaTeX kopieren');
    btn.title = 'Formel als LaTeX kopieren';
    btn.className = FORMEL_KNOPF;
    btn.textContent = 'Kopieren';
    btn.addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(formelZumKopieren(formel) ?? '');
            btn.textContent = '✓';
        } catch {
            btn.textContent = 'Fehler';
        }
        setTimeout(() => { btn.textContent = 'Kopieren'; }, 1500);
    });
    formel.appendChild(btn);
    return btn;
}

function leistenKnopf(leiste, klasse, text, titel, aktion) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.setAttribute('aria-label', titel);
    btn.title = titel;
    btn.className = klasse;
    btn.textContent = text;
    btn.addEventListener('click', async () => {
        if (btn.disabled) return;
        btn.disabled = true;
        try {
            btn.textContent = await aktion();
        } catch {
            btn.textContent = 'Fehler';
        }
        setTimeout(() => { btn.textContent = text; btn.disabled = false; }, 1500);
    });
    leiste.appendChild(btn);
    return btn;
}

/**
 * „Code kopieren" und „SVG" in die Hover-Leiste eines gerenderten Diagramms.
 *
 * Die Quelle liegt in `data-source`. Mermaid wird fürs SVG im **hellen** Thema neu
 * gerendert (`mermaidSvgHell`); die Server-Diagramme (Schaltplan, Funktionsgraph)
 * kennen keinen Dunkelmodus und gehen so, wie sie dastehen.
 */
export function diagrammKnoepfe(leiste, block, art, klasse) {
    leistenKnopf(leiste, klasse, 'Code kopieren', 'Quelltext des Diagramms kopieren', async () => {
        await navigator.clipboard.writeText(block.dataset.source ?? '');
        return '✓ Kopiert';
    });
    leistenKnopf(leiste, klasse, 'SVG', 'Als SVG-Datei herunterladen', async () => {
        const svg = art === 'mermaid'
            ? await mermaidSvgHell(block.dataset.source ?? '')
            : block.querySelector('svg').outerHTML;
        triggerDownload(svgDatei(svg), SVG_DATEINAME[art]);
        return '✓ SVG';
    });
}
