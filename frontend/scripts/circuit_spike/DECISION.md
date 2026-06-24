# CircuiTikZ-Render-Spike — Entscheidung D6 (Phase 15, Schritt 3)

**Datum:** 2026-06-24. **Frage:** Wie rendern wir elektrische Schaltpläne (Schaltungen)
im Chat? Mermaid kann das nicht; die LLM-naheliegende Notation ist **CircuiTikZ** (TikZ/PGF),
die eine TeX-Engine braucht.

## Befund (recherchiert + hands-on getestet)
- **circuitikz wird von den TikZJax-WASM-Builds explizit unterstützt** (obsidian-tikzjax /
  `@rod2ik/tikzjax` / `node-tikzjax` listen `circuitikz` neben `chemfig`, `pgfplots`, `tikz-cd`).
- **Hands-on bestätigt** (`eval.mjs`, `node-tikzjax` = pure Node + WASM, gleiche Engine wie
  die Browser-Variante): 3/3 repräsentative Schul-Schaltungen (Reihen-/Parallelschaltung,
  Schalter + Amperemeter) → **valides SVG in ~0,3–0,5 s**. Eine Reihenschaltung ergab z. B.
  5 `<path>`, 7 `<g>`, viewBox 218×105 — eine echte Schaltung, kein Fehler-Glyph.
- Engine-Gewicht: ~5 MB WASM (955 KB JS + 454 KB WASM + ~1,1 MB Memory-Dump + Pakete),
  lazy-ladbar (vergleichbar mit Mermaid ~6 MB, das wir bereits lazy laden).

## Zwei Deployment-Wege (gleiche Engine)
| | Client (Browser-TikZJax) | Server (`node-tikzjax`) |
|---|---|---|
| Wo | WASM-TeX im Browser (Web Worker) | WASM-TeX in Node → SVG zurück |
| Fit zum Stack | **natürlich** (Frontend-Dep, spiegelt Mermaid/KaTeX) | Backend ist **Python** → bräuchte Node-Sidecar |
| Client-Gewicht | +~5 MB lazy WASM | nur SVG (~2 KB) |
| Caching | pro Client | zentral (Hash → SVG), `node-tikzjax` exportiert `hashCode` |
| Render-Last | im Browser | Backend-CPU |

## Entscheidung (Empfehlung)
**Client-seitig (Browser-TikZJax), in Phase 15 (Schritt 4).** Begründung: spiegelt exakt das
bereits etablierte Mermaid-Muster (lazy WASM + Platzhalter + async Svelte-Action), **kein
Backend-/Infra-Umbau**. Der Server-Weg ist attraktiv (leichte Clients, zentrales Caching),
scheitert hier aber am Stack-Bruch: unser Backend ist Python, `node-tikzjax` ist Node → bräuchte
einen Node-Sidecar. Damit Folge-Optimierung, falls das Client-Gewicht/Tempo zum Problem wird.

Damit löst sich auch **D4**: kuratierte Schaltzeichen im Knoten = CircuiTikZ-Snippets über
dieselbe Pipeline (kein separates SVG-Handling).

## Offene Risiken für Schritt 4 (Umsetzung)
1. **Browser-/Vite-/SvelteKit-Integration** der WASM+Worker-Assets ist noch **nicht** hands-on
   validiert (der Spike bestätigte die *Engine* via Node, nicht die Browser-Bundling-Kette).
   Erste Implementierungsaufgabe: TikZJax in Vite zum Laufen bringen (Asset-Pfade, Worker).
2. **Runaway-TeX:** TeX ist turing-vollständig → Endlosschleife möglich. Im Web Worker (UI
   bleibt frei), aber ein **Timeout/Worker-Kill** ist Pflicht.
3. **Zweites schweres Lazy-Bundle** (~5 MB zusätzlich zu Mermaids ~6 MB). Beide lazy/gecacht;
   selten beide in einer Antwort. Schmaleres Einsatzfeld (Physik/NwT) als Mathe/Mermaid.
