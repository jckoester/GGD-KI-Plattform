// Gemeinsame Render-Helfer: TeX-Wrapping, MathJax-Mathe (→ SVG), bounded Cache.
import crypto from 'node:crypto';
import { mathjax } from 'mathjax-full/js/mathjax.js';
import { TeX } from 'mathjax-full/js/input/tex.js';
import { SVG } from 'mathjax-full/js/output/svg.js';
import { liteAdaptor } from 'mathjax-full/js/adaptors/liteAdaptor.js';
import { RegisterHTMLHandler } from 'mathjax-full/js/handlers/html.js';
import { AllPackages } from 'mathjax-full/js/input/tex/AllPackages.js';

export const sha256 = (s) => crypto.createHash('sha256').update(s).digest('hex');

// Umschließt die CircuiTikZ-Quelle zum vollständigen TeX-Dokument. Die Quelle enthält
// üblicherweise \begin{circuitikz}…\end{circuitikz}; \usepackage muss vor \begin{document}.
export function wrapCircuit(source) {
  return `\\usepackage{circuitikz}\n\\begin{document}\n${source}\n\\end{document}`;
}

// MathJax TeX→SVG. Für den PDF-Export (D5): **self-contained SVG** (fontCache:'none', Glyphen als
// Pfade) — weasyprint bettet es ohne CSS/Font-Abhängigkeit perfekt ein. `AllPackages` enthält
// mhchem (\ce{}/\pu{}). MathJax ist nicht turing-vollständig → im Hauptthread, kein Runaway.
const _adaptor = liteAdaptor();
RegisterHTMLHandler(_adaptor);
const _mjDoc = mathjax.document('', {
  InputJax: new TeX({ packages: AllPackages }),
  OutputJax: new SVG({ fontCache: 'none' }),
});

export function renderMath(tex, display = false) {
  const node = _mjDoc.convert(tex, { display: !!display });
  // Nur das <svg> (trägt selbst vertical-align + ex-Sizing für die Inline-Baseline) —
  // ohne den <mjx-container>-Wrapper.
  return _adaptor.outerHTML(_adaptor.firstChild(node));
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
