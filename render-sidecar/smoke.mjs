// Smoke-Test (Phase 17, Schritt 1): rendert die 3 Spike-Schaltungen über den Worker-Pool
// + ein KaTeX-Mathe- und ein mhchem-Sample. Prüft die Engine, nicht den HTTP-Layer.
//   node smoke.mjs   (bzw. npm run smoke)
import { CircuitRenderPool } from './pool.mjs';
import { wrapCircuit, renderMath } from './render.mjs';

// Schaltungs-Körper (das, was zwischen \begin{document} und \end{document} steht) —
// entspricht den Spike-Fällen (frontend/scripts/circuit_spike/eval.mjs).
const circuits = [
  {
    name: 'Reihenschaltung (R1, R2, Lampe)',
    tex: String.raw`\begin{circuitikz}
\draw (0,0) to[battery1, l=$U$] (0,3)
  to[R, l=$R_1$] (3,3)
  to[R, l=$R_2$] (6,3)
  to[lamp, l=$L$] (6,0)
  to[short] (0,0);
\end{circuitikz}`,
  },
  {
    name: 'Parallelschaltung (R1 || R2)',
    tex: String.raw`\begin{circuitikz}
\draw (0,0) to[battery1, l=$U$] (0,3) -- (3,3);
\draw (3,3) to[R, l=$R_1$] (3,0) -- (0,0);
\draw (3,3) -- (5,3) to[R, l=$R_2$] (5,0) -- (3,0);
\end{circuitikz}`,
  },
  {
    name: 'Schalter + Amperemeter',
    tex: String.raw`\begin{circuitikz}
\draw (0,0) to[battery1, l=$U$] (0,3)
  to[switch, l=$S$] (3,3)
  to[ammeter, l=$A$] (6,3)
  to[R, l=$R$] (6,0)
  to[short] (0,0);
\end{circuitikz}`,
  },
];

const pool = new CircuitRenderPool({ size: 2, timeoutMs: 20000 });
let allOk = true;

for (const c of circuits) {
  const t0 = performance.now();
  try {
    const svg = await pool.render(wrapCircuit(c.tex));
    const ms = Math.round(performance.now() - t0);
    const ok = svg.trimStart().startsWith('<svg') && svg.length > 300 && svg.includes('path');
    console.log(`${ok ? '✓' : '✗'} ${c.name}: ${ms} ms, SVG ${svg.length} B`);
    allOk = allOk && ok;
  } catch (e) {
    console.log(`✗ ${c.name}: FEHLER — ${String(e.message ?? e).slice(0, 200)}`);
    allOk = false;
  }
}

// KaTeX-Mathe + mhchem
try {
  const math = renderMath(String.raw`\frac{-b \pm \sqrt{b^2 - 4ac}}{2a}`, true);
  const okM = math.includes('katex') && math.includes('</math>'); // htmlAndMathml
  console.log(`${okM ? '✓' : '✗'} KaTeX Mathe: ${math.length} B`);
  allOk = allOk && okM;

  const chem = renderMath(String.raw`\ce{2 H2 + O2 -> 2 H2O}`, false);
  const okC = chem.includes('katex');
  console.log(`${okC ? '✓' : '✗'} KaTeX mhchem: ${chem.length} B`);
  allOk = allOk && okC;
} catch (e) {
  console.log(`✗ KaTeX: FEHLER — ${String(e.message ?? e).slice(0, 200)}`);
  allOk = false;
}

await pool.destroy();
console.log(allOk ? '\nSMOKE OK' : '\nSMOKE FAILED');
process.exit(allOk ? 0 : 1);
