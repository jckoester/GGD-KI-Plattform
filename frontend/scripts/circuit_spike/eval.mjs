// CircuiTikZ-Render-Spike (Phase 15, Schritt 3) — D6.
//
// Frage: Lässt sich CircuiTikZ über die TikZJax-WASM-Engine rendern (für Schaltpläne
// im Chat)? Getestet mit `node-tikzjax` (pure Node + WASM, DERSELBE Engine-/Paketsatz
// wie die Browser-Variante TikZJax — wenn circuitikz hier rendert, rendert es auch
// client-seitig).
//
// Ausführen:  npm install node-tikzjax && node eval.mjs
// (node-tikzjax wird NICHT mit eingecheckt — ~5 MB WASM.)

import * as mod from 'node-tikzjax';
const tex2svg = mod.default?.default ?? mod.default; // CJS/ESM-Interop

// Repräsentative Schul-Schaltungen (Reihen-/Parallelschaltung + Grundbauteile).
const cases = [
  { name: 'Reihenschaltung (R1, R2, Lampe)', tex: String.raw`
\usepackage{circuitikz}
\begin{document}
\begin{circuitikz}
\draw (0,0) to[battery1, l=$U$] (0,3)
  to[R, l=$R_1$] (3,3)
  to[R, l=$R_2$] (6,3)
  to[lamp, l=$L$] (6,0)
  to[short] (0,0);
\end{circuitikz}
\end{document}` },
  { name: 'Parallelschaltung (R1 || R2)', tex: String.raw`
\usepackage{circuitikz}
\begin{document}
\begin{circuitikz}
\draw (0,0) to[battery1, l=$U$] (0,3) -- (3,3);
\draw (3,3) to[R, l=$R_1$] (3,0) -- (0,0);
\draw (3,3) -- (5,3) to[R, l=$R_2$] (5,0) -- (3,0);
\end{circuitikz}
\end{document}` },
  { name: 'Schalter + Amperemeter', tex: String.raw`
\usepackage{circuitikz}
\begin{document}
\begin{circuitikz}
\draw (0,0) to[battery1, l=$U$] (0,3)
  to[switch, l=$S$] (3,3)
  to[ammeter, l=$A$] (6,3)
  to[R, l=$R$] (6,0)
  to[short] (0,0);
\end{circuitikz}
\end{document}` },
];

for (const c of cases) {
  const t0 = performance.now();
  try {
    const svg = await tex2svg(c.tex);
    const ms = Math.round(performance.now() - t0);
    const ok = svg.trimStart().startsWith('<svg') && svg.length > 300 && svg.includes('path');
    console.log(`${ok ? '✓' : '?'} ${c.name}: ${ms} ms, SVG ${svg.length} Bytes, valide=${ok}`);
  } catch (e) {
    const ms = Math.round(performance.now() - t0);
    console.log(`✗ ${c.name}: FEHLER nach ${ms} ms — ${String(e.message ?? e).slice(0, 240)}`);
  }
}
