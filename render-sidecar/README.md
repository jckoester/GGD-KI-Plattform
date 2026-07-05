# render-sidecar (Phase 17)

Interner Server-Render-Dienst: **CircuiTikZ → SVG** (via `node-tikzjax`, WASM-TeX) und
**KaTeX-Mathe** (inkl. mhchem). Reines Rendering — kein LLM, kein Provider, keine Moderation,
keine Kosten. **Nur vom Backend aufgerufen, nie öffentlich exponieren** (localhost/compose-Netz).

Hintergrund/Entscheidungen: `Plaene/Artefakte-und-Server-Rendering-Phase-17-Plan.md`.

## Warum ein eigener Node-Dienst?

Das Backend ist Python; `node-tikzjax` (die einzige heute funktionierende circuitikz-fähige
Engine) ist Node-only. Ein **langlaufender** Dienst hält die ~5 MB WASM-Engine warm (schnelle
Folge-Renders). CircuiTikZ-Renders laufen in einem **Worker-Pool**: TeX ist turing-vollständig →
ein Runaway-Snippet wird per Timeout durch **Terminieren des Workers** hart gestoppt, der Dienst
bleibt gesund. KaTeX läuft im Hauptthread (nicht turing-vollständig, kein Runaway-Risiko).

## Endpunkte

| Methode | Pfad | Body | Antwort |
|---|---|---|---|
| GET | `/health` | — | `{ status, pool }` |
| POST | `/render/circuit` | `{ source }` (CircuiTikZ, i. d. R. `\begin{circuitikz}…\end{circuitikz}`) | `{ svg }` \| `{ error }` |
| POST | `/render/math` | `{ tex, display }` | `{ html }` \| `{ error }` (KaTeX, htmlAndMathml) |

Bei Cache-Treffer zusätzlich `cached: true`. Fehler beim Rendern → HTTP 422 mit `{ error }`.

## Dev

```bash
cd render-sidecar
npm install            # node-tikzjax + katex (~5 MB WASM, nicht eingecheckt)
npm run smoke          # Engine-Smoke: 3 Schaltungen + KaTeX/mhchem
npm start              # Server (Default 127.0.0.1:3200)
```

Lokal wie LiteLLM starten (eigenes Terminal). Das Backend spricht ihn über
`RENDER_SIDECAR_URL` an (Schritt 2). Prod-Betrieb (docker-compose-Service, Health-Check,
Ressourcen-Limits): Schritt 8.

## Konfiguration (Env)

| Variable | Default | Bedeutung |
|---|---|---|
| `RENDER_SIDECAR_HOST` | `127.0.0.1` | Bind-Host (intern lassen) |
| `RENDER_SIDECAR_PORT` | `3200` | Port |
| `RENDER_POOL_SIZE` | `2` | Worker-Pool = Concurrency-Cap für CircuiTikZ |
| `RENDER_TIMEOUT_MS` | `10000` | harter Render-Timeout (Worker-Kill bei Runaway) |
| `RENDER_CACHE_MAX` | `500` | In-Prozess-LRU-Cache-Einträge (Haupt-Cache liegt im Backend) |
| `RENDER_MAX_BODY` | `131072` | max. Request-Body (Bytes) |
