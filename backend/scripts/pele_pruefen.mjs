// Hilfe für diagramme_auswerten.py (0.36): Mermaid-Quellen roh und repariert mit Pele prüfen.
// Liest eine JSON-Liste von Quellen von stdin, schreibt je Quelle {roh, repariert, fehler}.
// Pele und die Reparatur kommen aus dem Render-Sidecar — dieselben, die der Export benutzt.
import { render } from '../../render-sidecar/node_modules/pele/dist/pele.js';
import { mermaidReparieren } from '../../render-sidecar/peleHilfen.mjs';

const quellen = JSON.parse(await new Promise((ok) => {
  let d = ''; process.stdin.on('data', (c) => (d += c)); process.stdin.on('end', () => ok(d));
}));
const geht = (q) => { try { render(q); return [true, null]; } catch (e) { return [false, String(e.message).split('\n')[0]]; } };
console.log(JSON.stringify(quellen.map((q) => {
  const [roh] = geht(q);
  const [repariert, fehler] = geht(mermaidReparieren(q));
  return { roh, repariert, fehler };
})));
