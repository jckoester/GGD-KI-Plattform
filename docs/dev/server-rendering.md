# Server-Rendering (Phase 17)

Serverseitiges Rendern von Inhalten, die der Browser nicht (sicher) selbst rendern kann:

- **CircuiTikZ-Schaltpläne** (```circuitikz) — brauchen eine TeX-Engine.
- **Funktionsgraphen** (```plot) — deklarative Spec → matplotlib.
- **Mathe im PDF-Export** — `$…$`/`$$…$$` → MathJax-SVG (weasyprint führt kein KaTeX/JS aus).

Reines Rendering: **kein LLM, kein Provider, keine Kosten, keine Moderation.** Das LLM (bzw.
die Kurator:in) liefert nur eine **Beschreibung** (CircuiTikZ-Quelle, Plot-Spec), nie
ausführbaren Code.

## Bausteine im Überblick

```
Chat/Knoten (Browser)            PDF-Export (Backend)
   renderServerBlocks               render_markdown_for_pdf
        │  POST /api/render/{kind}        │
        ▼                                 ▼
   app/render/router.py  ──►  app/render/service.py (Registry + Cache rendered_svg)
                                    │              │
                            circuit │              │ plot
                                    ▼              ▼
                     render-sidecar (Node)   app/render/plot.py (matplotlib, in-process)
                     node-tikzjax + MathJax
```

## Node-Render-Sidecar (`render-sidecar/`)

Eigener Node-Dienst, weil das Backend Python ist und die einzige heute funktionierende
circuitikz-fähige Engine (`node-tikzjax`) Node-only ist. **Nur intern erreichbar.**

- `server.mjs` — Node-`http`: `GET /health`, `POST /render/circuit`, `POST /render/math`.
- `pool.mjs` — **Worker-Pool** für CircuiTikZ: TeX ist turing-vollständig → per-Render-Timeout
  terminiert den Worker (Runaway-Kill) und startet einen frischen; Pool-Größe = Concurrency-Cap.
- `render.mjs` — `wrapCircuit` (TeX-Dokument) · `renderMath` = **MathJax → SVG**
  (`fontCache:'none'`, `AllPackages` inkl. mhchem; das `<svg>` trägt `vertical-align` + ex-Sizing
  für die Inline-Baseline) · `BoundedCache`.

Env: `RENDER_SIDECAR_HOST/PORT`, `RENDER_POOL_SIZE`, `RENDER_TIMEOUT_MS`, `RENDER_CACHE_MAX`,
`RENDER_MAX_BODY`.

## Backend-Render-Router (`app/render/`)

- `router.py` — `POST /render/{kind}` (Pseudonym-Auth). Antwort `{svg, cached, error}` — bei
  Fehlern immer ein **Fehler-Platzhalter-SVG** (`service.ERROR_SVG`), nie eine gesprengte Antwort.
- `service.py` — **Renderer-Registry** `RENDERERS = {"circuit": …, "plot": …}`. Ablauf:
  Hash → Cache-Treffer? → sonst Renderer → **nur Erfolge** in den Cache. `svg_hash(kind, source)`.
- `cache.py` — Tabelle `rendered_svg (hash PK, svg, created_at)` (content-adressiert,
  deterministisch). Aufräumen altersbasiert: `cleanup_rendered_svg` (Cron, siehe unten).
- `sidecar.py` — httpx-Client zum Sidecar (`render_circuit`, `render_math`); Timeout/Fehler →
  `RenderError` (`app/render/errors.py`).
- `plot.py` — Plots **in-process** (kein Sidecar): `lark`-Grammatik (Präzedenz `^`>unär->`*`/`/`>
  `+`/`-`, explizites `*`, nur `x`/`pi`/`e`/Funktions-Whitelist) → Transformer baut eine
  vektorisierte **numpy**-Funktion (**eval-frei**); `PlotSpec` (Pydantic/YAML); matplotlib
  **OO-`Figure`-API** (thread-safe) in `to_thread` mit Timeout → SVG. `**` wird als `^` akzeptiert.

## Frontend (`renderServerBlocks`)

`markdown.js` erzeugt für ```circuitikz/```plot einen Platzhalter (`circuit-block`/`plot-block`,
Quelle escaped). Die **generische** Action `renderServerBlocks` (`serverRender.js`) POSTet die
Quelle an `/api/render/{kind}`, sanitisiert das SVG (`sanitizeSvg`) und injiziert es.
Eingebunden in `MessageBubble.svelte` (Chat) + `knowledge/[id]/+page.svelte` (Knoten).

**`sanitizeSvg`-Falle:** `ADD_TAGS:['use']` + `ADD_ATTR:['xlink:href','href']` sind nötig
(matplotlib rendert Text/Marker als Glyphen-`<use xlink:href="#…">`). **Keine** eigene
`ALLOWED_URI_REGEXP` setzen — die lässt DOMPurify auch das `d`-Attribut der Pfade prüfen →
`d` wird gestrippt → leeres Bild.

## PDF-Prärender (D5, `app/render/export.py`)

weasyprint führt kein JS aus → `render_markdown_for_pdf` prä-rendert **vor** weasyprint:
`$…$`→MathJax-SVG (Sidecar), ```circuitikz→Sidecar, ```plot→matplotlib; token-basiert
(markdown-it-py + `mdit-py-plugins` `dollarmath`, respektiert Code-Kontext). `…_inline_for_pdf`
für kompakte Kontexte (Tabellenzellen, ohne `<p>`).

**weasyprint-Falle:** weasyprint kennt SVG-`style="fill:…;stroke:…"` nicht ("unknown property")
→ Plots würden schwarz gefüllt. `_svg_style_to_attrs` schreibt Präsentations-Properties aus dem
`style` in echte **Attribute** um (`vertical-align` bleibt im style). Eingehängt in
`curriculum_export._build_pdf_kapitel` (konkretisierung) und `lesson_export.export_pdf`
(beschreibung/stundenziel).

## ```plot-Spec (v1)

```plot
functions:
  - f(x) = x^2 - 2      # optionaler Name; explizites *, nur x; ^ oder ** als Potenz
  - g(x) = sin(x)
domain: [-4, 4]
range: [-2, 8]          # optional (sonst Autoskalierung)
points: [[1, -1, "P"]]  # [x, y] oder [x, y, "Label"]
grid: true
asymptotes: [0]         # optional: vertikale Linien
```

Erlaubte Funktionen: sin, cos, tan, asin, acos, atan, sinh, cosh, tanh, exp, ln, log (=ln),
log10, lg (=log10), sqrt, abs, sign, floor, ceil. Konstanten: pi, e. Erweiterungen (Ableitungen,
Ungleichungen, Parameter-/implizite Kurven, Scatter) sind bewusst v1-out (Todo.md).

## Betrieb & Sicherheit

- **Prod:** Sidecar als docker-compose-Service `render-sidecar` (Health-Check, `restart`,
  Ressourcen-Limits, kein `ports:` → intern). Backend erreicht ihn über `RENDER_SIDECAR_URL`.
  Backend braucht `MPLCONFIGDIR` (schreibbar, matplotlib-Font-Cache).
- **Dev:** Sidecar lokal starten (eigenes Terminal, wie LiteLLM): `cd render-sidecar && npm start`.
  Läuft er nicht, liefern Render-Aufrufe den Fehler-Platzhalter (Chat) bzw. den Quelltext (PDF).
- **Sicherheit:** TeX-Runaway → Timeout/Worker-Kill + Concurrency-Cap; WASM-Sandbox (kein
  FS-/Netzzugriff). Plot-Ausdrücke eval-frei (lark→numpy). Endpoint-Rate-Limit ist bewusst
  **nicht** hier, sondern im Sicherheits-Audit-Track.
- **Cache-Cleanup:** `scripts/cleanup_rendered_svg.py` (Cron, altersbasiert über
  `render_cache_max_age_days`).
