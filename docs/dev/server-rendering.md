# Server-Rendering (Phase 17, Strukturformeln 0.30, Mermaid 0.36)

Serverseitiges Rendern von Inhalten, die der Browser nicht (sicher) selbst rendern kann:

- **CircuiTikZ-Schaltpläne** (```circuitikz) — brauchen eine TeX-Engine.
- **Funktionsgraphen** (```plot) — deklarative Spec → matplotlib.
- **Strukturformeln** (```smiles, seit 0.30) — SMILES → RDKit, freie Elektronenpaare berechnet.
- **Mathe im PDF-Export** — `$…$`/`$$…$$` → MathJax-SVG (weasyprint führt kein KaTeX/JS aus).

Reines Rendering: **kein LLM, kein Provider, keine Kosten, keine Moderation.** Das LLM (bzw.
die Kurator:in) liefert nur eine **Beschreibung** (CircuiTikZ-Quelle, Plot-Spec), nie
ausführbaren Code (Strukturformeln: SMILES).

## Bausteine im Überblick

```
Chat/Knoten (Browser)            PDF-Export (Backend)
   renderServerBlocks               render_markdown_for_pdf
        │  POST /api/render/{kind}        │
        ▼                                 ▼
   app/render/router.py  ──►  app/render/service.py (Registry + Cache rendered_svg)
                                    │              │
                   circuit, mermaid │              │ plot, smiles
                                    ▼              ▼
                     render-sidecar (Node)   app/render/plot.py (matplotlib, in-process)
                     node-tikzjax + MathJax  app/render/smiles.py (RDKit, in-process)
                     + Pele (Mermaid)
```

## Node-Render-Sidecar (`render-sidecar/`)

Eigener Node-Dienst, weil das Backend Python ist und die einzige heute funktionierende
circuitikz-fähige Engine (`node-tikzjax`) Node-only ist. **Nur intern erreichbar.**

- `server.mjs` — Node-`http`: `GET /health`, `POST /render/circuit`, `POST /render/math`,
  `POST /render/mermaid` (seit 0.36).
- `mermaid.mjs` — **Pele** (`github.com/obsidianmd/pele`, MIT) rendert ohne DOM, synchron, unter
  10 ms; deshalb im Hauptthread wie MathJax. Davor `mermaidReparieren` (Klammern in Beschriftungen
  in Anführungszeichen), danach `festeFarben` (keine CSS-Variablen — Word und weasyprint werten
  `var()` nicht aus). `maxWidth: 620` (Satzspiegel): Pele setzt ein zu breites Diagramm neu,
  statt dass es geschrumpft wird.
- `peleHilfen.mjs` — **wortgleiche Kopie** von `frontend/src/lib/peleHilfen.js` (der Sidecar ist
  ein eigenes Paket mit eigenem Docker-Build). `peleHilfen.test.js` im Frontend prüft die
  Gleichheit; geändert wird im Frontend, dann kopiert.
- `pool.mjs` — **Worker-Pool** für CircuiTikZ: TeX ist turing-vollständig → per-Render-Timeout
  terminiert den Worker (Runaway-Kill) und startet einen frischen; Pool-Größe = Concurrency-Cap.
- `circuitikz.mjs` (seit 0.37, abhängigkeitsfrei) — `circuitikzAufbereiten` und `wrapCircuit`.
  Modelle schreiben CircuiTikZ selten so, wie node-tikzjax es braucht; die Aufbereitung macht
  daraus genau eine Umgebung im TeX-Dokument mit `\usepackage{amsmath}` und
  `\usepackage[european]{circuitikz}`:
  - Präambel (`\documentclass`, `\usepackage`, `\begin{document}`) wird entfernt; fehlt die
    Umgebung, wird sie ergänzt (eine `tikzpicture` bleibt).
  - `[american]`/`[US]` an der Umgebung und `\ctikzset{american}` fallen weg — europäische
    Symbole (DIN/IEC) sind Vorgabe.
  - **Schalter:** `switch`/`spst`/`closing switch`/`cspst` werden `nos` (Schulsymbol ohne
    Bogenpfeil), `opening switch`/`ospst` werden `ncs`.
  - **Zeichen**, die der TeX-Motor nicht kennt: schmale Leerzeichen (U+2007/2009/202F) werden
    normale, Ω/µ/μ/°/× werden `\ensuremath{…}`.

  ⚠️ **Im Sidecar steckt CircuiTikZ 1.0 (Februar 2020).** Neuere Namen wie `elmech` (Motor) gibt es
  nicht; der Baustein `schaltplaene` (`backend/app/assistants/bausteine/schaltplaene.md`) nennt
  nur geprüfte Namen, und der Smoke-Test zeichnet jede seiner Vorlagen. Eine neuere Fassung hieße
  Paketdateien in `tex_files.tar.gz` tauschen oder TeX Live im Container (Todo).
- `render.mjs` — `wrapCircuit` (aus `circuitikz.mjs`) · `renderMath` = **MathJax → SVG**
  (`fontCache:'none'`, `AllPackages` inkl. mhchem; das `<svg>` trägt `vertical-align` + ex-Sizing
  für die Inline-Baseline) · `BoundedCache`.

Env: `RENDER_SIDECAR_HOST/PORT`, `RENDER_POOL_SIZE`, `RENDER_TIMEOUT_MS`, `RENDER_CACHE_MAX`,
`RENDER_MAX_BODY`.

## Backend-Render-Router (`app/render/`)

- `router.py` — `POST /render/{kind}` (Pseudonym-Auth). Antwort `{svg, cached, error}` — bei
  Fehlern immer ein **Fehler-Platzhalter-SVG** (`service.ERROR_SVG`), nie eine gesprengte Antwort.
- `service.py` — **Renderer-Registry** `RENDERERS = {"circuit", "plot", "smiles", "mermaid"}`. Ablauf:
  Hash → Cache-Treffer? → sonst Renderer → **nur Erfolge** in den Cache. `svg_hash(kind, source)`.
- `cache.py` — Tabelle `rendered_svg (hash PK, svg, created_at)` (content-adressiert,
  deterministisch). Aufräumen altersbasiert: `cleanup_rendered_svg` (Cron, siehe unten).
  **`RENDERER_FASSUNG`** (seit 0.30): Ändert sich die Zeichnung eines Renderers, erhöhen Sie
  dort seine Zahl — sie geht in den Hash ein, sonst liefert der Cache zur gleichen Quelle weiter
  das alte Bild. Stand 0.37: `smiles` 3, `plot` 2 (Achsen-Standards), `circuit` 2 (europäische
  Symbole, Aufbereitung, Schulschalter); Mermaid hat keine Fassung.
- `sidecar.py` — httpx-Client zum Sidecar (`render_circuit`, `render_math`, `render_mermaid`, alle
  über `_post_svg`); Timeout/Fehler →
  `RenderError` (`app/render/errors.py`).
- `plot.py` — Plots **in-process** (kein Sidecar): `lark`-Grammatik (Präzedenz `^`>unär->`*`/`/`>
  `+`/`-`, explizites `*`, nur `x`/`pi`/`e`/Funktions-Whitelist) → Transformer baut eine
  vektorisierte **numpy**-Funktion (**eval-frei**); `PlotSpec` (Pydantic/YAML); matplotlib
  **OO-`Figure`-API** (thread-safe) in `to_thread` mit Timeout → SVG. `**` wird als `^` akzeptiert.
  **Aussehen (0.36):** ein Bündel `PlotStil` mit `STANDARD` — Achsen durch den Ursprung mit Pfeil
  und „x“/„y“, Teilstriche 1/2/2,5/5 × 10ⁿ, gleiche Einheit bei Spannenverhältnis ≤ 3 (Figur passt
  sich an), y-Bereich ohne `range` auf das 2-/98-%-Quantil gekappt, wenn Ausreißer ihn sprengen,
  Flexoki-Farben, Legende ab zwei Funktionen. `_zeichne()` ist vom SVG-Export getrennt; Tests
  prüfen Achsenwerte. Wer `STANDARD` ändert, erhöht `RENDERER_FASSUNG["plot"]`.

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

## Strukturformeln (```smiles, `app/render/smiles.py`)

In-process wie der Plot (`asyncio.to_thread` mit `smiles_render_timeout`). Eine Zeile je Reihe,
Moleküle als SMILES, Operatoren von Leerzeichen umgeben:

```smiles
darstellung: skelett
[O-]c1ccccc1 <-> O=C1C=CC=C[CH-]1
Essigsäure: CC(=O)O + Ethanol: OCC <=> CC(=O)OCC + O
```

- Operatoren `+`, `->`, `<=>` (Gleichgewicht), `<->` (Mesomerie), auch `→ ⇌ ↔`. SMILES enthält
  kein Leerzeichen; deshalb trennen Leerzeichen eindeutig, auch bei `[NH3+]`. `Name: SMILES`
  beschriftet (getrennt am letzten „: ").
- `darstellung:` in der ersten Zeile, Vorgabe **valenzstrich** (alle H, `C` beschriftet);
  `skelett` nur auf Wunsch.
- **Freie Elektronenpaare** zeichnet RDKit nicht. `freie_paare()` rechnet: Außenelektronen −
  Formalladung − `GetTotalValence()` − Radikalelektronen, halbiert. Die Striche gehen in die
  größten Winkellücken zwischen Bindungen **und** Beschriftung.
- **Grenzen:** 2000 Zeichen, 4 Reihen, 6 Moleküle je Reihe, 300 Zeichen je SMILES, 120 schwere
  Atome.
- **Teilfehler:** Ein Molekül, das RDKit nicht annimmt, wird ein gestrichelter Platzhalter mit
  seiner Quelle (`platzhalter()`); der Block scheitert erst, wenn kein Molekül gelingt.

**Fallen (alle aufgetreten):**

- **Keine Aromatizitäts-Erkennung** (`SANITIZE_ALL ^ SANITIZE_SETAROMATICITY`). Sonst legt
  RDKit die Doppelbindungen einer Grenzformel wie `O=C1C=CC=C[CH-]1` neu — und genau deren
  Lage ist die Aussage. Nur klein (aromatisch) geschriebene Ringe werden kekulisiert.
- **Maßstab über `scalingFactor`** (Bildpunkte je Å). `fixedBondLength` wirkt bei anpassbarer
  Zeichenfläche (`MolDraw2DSVG(-1, -1)`) nicht.
- **Lage der Beschriftung wird gelesen, nicht geschätzt:** `_beschriftung()` liest die
  Umrisse der Glyphen-Pfade `class='atom-N'` aus dem RDKit-SVG. Nah an der Atommitte = Symbol,
  weiter weg = angehängtes H, Ladung → belegte Richtung. Geschätzt stand ein Paar im H von „OH".
- **Eigene Atombeschriftung nur für ungeladenes C** — `atomLabels` ersetzt RDKits Beschriftung
  ganz; beim Carbanion verschwand sonst das Minus.
- **Flache Gruppen statt verschachtelter `<svg>`, Stile als Attribute** (`_innen()`):
  weasyprint und der SVG-Import von Word/LibreOffice verkraften beides sonst nicht; RDKit
  schreibt `style='…'` in einfachen Anführungszeichen, die `_svg_style_to_attrs` nicht erkennt.

**Export:** `export.py` und `app/export/prerender.py` kennen `smiles` wie `circuit`/`plot`.
Breite Reihen verkleinert `_hoechstens_seitenbreit` über `width`/`height` auf den Satzspiegel
(`SATZSPIEGEL_PX`) — CSS `max-width` ignoriert weasyprint hier. Office-Alternativtext
„Strukturformel".

**Prompt:** Der Absatz zu Strukturformeln steht in `config/pedagogy.yaml` (Abschnitt Grafiken,
`universal_base`), gemessen mit `backend/scripts/strukturformel_messung.py` (Szenarien
`scripts/szenarien/strukturformeln.yaml`; zählt einen Platzhalter weiter als Fehler).

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
