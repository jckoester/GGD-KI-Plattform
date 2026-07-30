// Render-Worker: rendert eine vollständige TeX-Quelle (inkl. \usepackage{circuitikz}
// + \begin{document}…\end{document}) über die node-tikzjax-WASM-Engine zu SVG.
//
// Läuft in einem worker_thread, damit ein Runaway-TeX (turing-vollständig) durch
// Terminieren des Workers hart gestoppt werden kann (Timeout im Pool). Die Engine
// wird beim ersten Render geladen und bleibt danach im Worker warm.
import { parentPort } from 'node:worker_threads';
import * as mod from 'node-tikzjax';

// CJS/ESM-Interop wie im Phase-15-Spike (frontend/scripts/circuit_spike/eval.mjs).
const tex2svg = mod.default?.default ?? mod.default;

parentPort.on('message', async ({ id, source }) => {
  try {
    const svg = await tex2svg(source);
    parentPort.postMessage({ id, svg });
  } catch (e) {
    parentPort.postMessage({ id, error: String(e?.message ?? e).slice(0, 500) });
  }
});
