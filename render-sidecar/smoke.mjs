// Smoke-Test (Phase 17, Schritt 1): rendert die 3 Spike-Schaltungen über den Worker-Pool
// + ein KaTeX-Mathe- und ein mhchem-Sample. Prüft die Engine, nicht den HTTP-Layer.
//   node smoke.mjs   (bzw. npm run smoke)
import { CircuitRenderPool } from './pool.mjs';
import { wrapCircuit, renderMath } from './render.mjs';
import { renderMermaid } from './mermaid.mjs';

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

// 0.37: Quelle wie von chat-komplex (ohne Umgebung) bzw. chat-standard ([american]) — die Aufbereitung
// in circuitikz.mjs muss beide zeichenbar machen.
for (const [name, tex] of [
  ['ohne Umgebung', String.raw`\draw (0,0) to[battery1,l=$U$] (0,3) to[R,l=$R$] (3,3) to[lamp] (3,0) -- (0,0);`],
  ['[american] mit Präambel', String.raw`\documentclass{standalone}
\usepackage{circuitikz}
\begin{document}
\begin{circuitikz}[american]
\draw (0,0) to[battery1] (0,3) to[R] (3,3) -- (3,0) -- (0,0);
\end{circuitikz}
\end{document}`],
]) {
  try {
    const svg = await pool.render(wrapCircuit(tex));
    console.log(`✓ Aufbereitung ${name}: SVG ${svg.length} B`);
  } catch (e) {
    console.log(`✗ Aufbereitung ${name}: FEHLER — ${String(e.message ?? e).slice(0, 120)}`);
    allOk = false;
  }
}

// 0.37: Jede Vorlage des Bausteins „Schaltpläne“ muss zeichnen — sonst brächte er dem Modell einen
// Plan bei, der scheitert. Die Datei liegt im Backend; im Docker-Image des Sidecars fehlt sie (übersprungen).
{
  const pfad = new URL('../backend/app/assistants/bausteine/schaltplaene.md', import.meta.url);
  const fs = await import('node:fs');
  if (fs.existsSync(pfad)) {
    const vorlagen = [...fs.readFileSync(pfad, 'utf8').matchAll(/```circuitikz\n([\s\S]*?)```/g)].map((m) => m[1]);
    let gut = 0;
    for (const v of vorlagen) {
      try { await pool.render(wrapCircuit(v)); gut++; } catch { console.log(`✗ Baustein-Vorlage: ${v.slice(0, 60)}…`); }
    }
    console.log(`${gut === vorlagen.length ? '✓' : '✗'} Baustein „Schaltpläne“: ${gut}/${vorlagen.length} Vorlagen zeichnen`);
    allOk = allOk && gut === vorlagen.length;
  } else {
    console.log('– Baustein „Schaltpläne“ nicht gefunden (Docker-Image) — übersprungen');
  }
}

// MathJax-Mathe (→ SVG) + mhchem
try {
  const math = renderMath(String.raw`\frac{-b \pm \sqrt{b^2 - 4ac}}{2a}`, true);
  const okM = math.trimStart().startsWith('<svg') && math.includes('<path');
  console.log(`${okM ? '✓' : '✗'} MathJax Mathe: ${math.length} B`);
  allOk = allOk && okM;

  const chem = renderMath(String.raw`\ce{2 H2 + O2 -> 2 H2O}`, false);
  const okC = chem.trimStart().startsWith('<svg') && chem.includes('<path');
  console.log(`${okC ? '✓' : '✗'} MathJax mhchem: ${chem.length} B`);
  allOk = allOk && okC;
} catch (e) {
  console.log(`✗ MathJax: FEHLER — ${String(e.message ?? e).slice(0, 200)}`);
  allOk = false;
}

// Mermaid (Pele, 0.36): Reparatur der Klammern, feste Farben, kaputte Quelle wirft
try {
  const svg = renderMermaid('flowchart LR\n  A[Nitrat (NO₃⁻)] -->|Aufnahme (Wurzel)| B[Pflanze]');
  const okP = svg.startsWith('<svg') && svg.includes('Nitrat') && !svg.includes('var(');
  console.log(`${okP ? '✓' : '✗'} Mermaid (Pele): ${svg.length} B, ohne var()`);
  const lang = renderMermaid('flowchart LR\n' + Array.from({ length: 12 }, (_, i) => `  S${i}[Schritt ${i}] --> S${i + 1}[Schritt ${i + 1}]`).join('\n'));
  const breite = Number(lang.match(/width="([\d.]+)"/)[1]);
  console.log(`${breite <= 620 ? '✓' : '✗'} Lange LR-Kette passt auf die Seite: ${breite} px`);
  allOk = allOk && breite <= 620;
  allOk = allOk && okP;
  let wirft = false;
  try { renderMermaid('flowchart LR\n  A[Start --> B'); } catch { wirft = true; }
  console.log(`${wirft ? '✓' : '✗'} Mermaid kaputt → Fehler`);
  allOk = allOk && wirft;
} catch (e) {
  console.log(`✗ Mermaid: FEHLER — ${String(e.message ?? e).slice(0, 200)}`);
  allOk = false;
}

await pool.destroy();
console.log(allOk ? '\nSMOKE OK' : '\nSMOKE FAILED');
process.exit(allOk ? 0 : 1);
