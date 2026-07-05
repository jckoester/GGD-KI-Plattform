// Gemeinsame Render-Helfer: TeX-Wrapping, KaTeX-Mathe, bounded Cache.
import crypto from 'node:crypto';
import katex from 'katex';
import 'katex/contrib/mhchem'; // \ce{}/\pu{} — Parität zum Frontend (markdown.js)

export const sha256 = (s) => crypto.createHash('sha256').update(s).digest('hex');

// Umschließt die CircuiTikZ-Quelle zum vollständigen TeX-Dokument. Die Quelle enthält
// üblicherweise \begin{circuitikz}…\end{circuitikz}; \usepackage muss vor \begin{document}.
export function wrapCircuit(source) {
  return `\\usepackage{circuitikz}\n\\begin{document}\n${source}\n\\end{document}`;
}

// KaTeX rendert im Hauptthread: nicht turing-vollständig, schnell, kein Runaway-Risiko.
// Optionen spiegeln den Frontend-Renderer (output htmlAndMathml, lenient).
export function renderMath(tex, display = false) {
  return katex.renderToString(tex, {
    displayMode: !!display,
    output: 'htmlAndMathml',
    throwOnError: false,
  });
}

// Kleiner LRU-Cache (Map behält Einfügereihenfolge; get schiebt ans Ende).
export class BoundedCache {
  constructor(max = 500) { this.max = max; this.map = new Map(); }
  get(k) {
    if (!this.map.has(k)) return undefined;
    const v = this.map.get(k);
    this.map.delete(k); this.map.set(k, v);
    return v;
  }
  set(k, v) {
    if (this.map.has(k)) this.map.delete(k);
    else if (this.map.size >= this.max) this.map.delete(this.map.keys().next().value);
    this.map.set(k, v);
  }
}
