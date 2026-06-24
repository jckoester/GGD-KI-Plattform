# Frontend-Konventionen

## Svelte 5

Das Projekt verwendet **Svelte 5** mit der Runes-API. Svelte-4-Syntax ist
veraltet und darf in neuem Code nicht mehr verwendet werden.

### Verwenden

```svelte
<script>
  // Props
  let { value, onChange } = $props()

  // Reaktiver Zustand
  let count = $state(0)

  // Berechneter Wert
  let doubled = $derived(count * 2)

  // Seiteneffekt (reagiert auf Abhängigkeiten)
  $effect(() => {
    document.title = `Zähler: ${count}`
  })
</script>

<!-- Event-Handler -->
<button onclick={() => count++}>+</button>

<!-- Slots in Layouts: -->
{@render children()}
```

### Nicht mehr verwenden

```svelte
<!-- ❌ Svelte 4 — nicht in neuem Code -->
export let value          → let { value } = $props()
let x = $state(...)       → korrekt
$: doubled = x * 2        → let doubled = $derived(x * 2)
on:click={fn}             → onclick={fn}
<slot />                  → {@render children()}
```

## CSS: Semantische Farb-Tokens

`frontend/src/routes/layout.css` definiert zwei Abstraktionsebenen:

1. **Rohe Palette** (`--color-base-100`, `--color-blue-600`, …) — das konkrete
   Farbschema (aktuell: fexoki). Wird ausgetauscht, wenn das Schema wechselt.
2. **Semantische Tokens** (`--color-light-tx`, `--color-dark-bg`, …) — abstrahieren
   Bedeutung von konkreten Farben.

**Regel: Komponenten verwenden ausschließlich semantische Tokens.**

| Verwendung | Light-Klasse | Dark-Klasse |
|-----------|-------------|------------|
| Seitenhintergrund | `bg-light-bg` | `dark:bg-dark-bg` |
| Erhöhter Hintergrund | `bg-light-bg-2` | `dark:bg-dark-bg-2` |
| Primärer Text | `text-light-tx` | `dark:text-dark-tx` |
| Sekundärer Text | `text-light-tx-2` | `dark:text-dark-tx-2` |
| Rahmen / UI-Elemente | `border-light-ui-3` | `dark:border-dark-ui-3` |
| Primärfarbe (Buttons) | `bg-primary` | `dark:bg-primary-dark` |
| Links / Akzent | `text-light-bl` | `dark:text-dark-bl` |
| Fehler | `text-light-re` | `dark:text-dark-re` |

```svelte
<!-- ✅ Richtig -->
<p class="text-light-tx dark:text-dark-tx">...</p>

<!-- ❌ Falsch — Palette direkt oder Tailwind-Standardfarben -->
<p class="text-gray-900 dark:text-gray-100">...</p>
<p class="text-base-content">...</p>
```

## Routing

Alle Route-Pfade sind **englisch**, Kleinschreibung, Bindestriche statt Unterstriche.

```
(app)/          → normale Nutzerrouten (Auth-Guard im Layout)
(admin)/        → Admin-only-Routen (zusätzliche Rollen-Prüfung)
info/[key]/     → statische Texte (impressum, datenschutz, regeln)
```

Die vollständige Routen-Tabelle steht in `CLAUDE.md`.

Neue Routen brauchen eine `+page.js` (oder `+page.server.js`) mit mindestens:
```js
export function load() {
  return { title: 'Seitentitel' }
}
```

## API-Calls (`frontend/src/lib/api.js`)

Alle Backend-Anfragen laufen über `api.js`. Kein direktes `fetch` in Komponenten.

```js
// Alle Calls gehen gegen /api (Vite-Dev-Proxy / nginx in Produktion)
const BASE = '/api'

// Fehlerbehandlung
class ApiError extends Error {
  constructor(status, detail) { ... }
}

// credentials: 'include' immer setzen — JWT als HttpOnly-Cookie
const res = await fetch(`${BASE}/endpoint`, {
  credentials: 'include',
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
})
```

## SSE-Streaming (`streamChat` in api.js)

`streamChat()` ist ein **async generator** — er liefert Event-Objekte:

```js
for await (const event of streamChat(messages, conversationId, modelId)) {
  if (event.type === 'start')  { /* conversationId aus Header */ }
  if (event.type === 'token')  { /* Token anhängen */ }
  if (event.type === 'title')  { /* Gesprächstitel aktualisieren */ }
  if (event.type === 'cost')   { /* Kosten anzeigen */ }
}
```

Die zugehörigen SSE-Events und ihr Format sind in
[chat-streaming.md](chat-streaming.md) dokumentiert.

## Rich-Rendering im Markdown (KaTeX, Mermaid)

Ein **zentraler** Renderer `frontend/src/lib/markdown.js` (`renderMarkdown`) speist Chat
(`MessageBubble`), Wissensgraph (`/knowledge/[id]`), Curriculum-Tabelle und Hilfeseiten —
eine Erweiterung dort wirkt überall. Pipeline: `marked` → `DOMPurify.sanitize`
(+ highlight.js für Codeblöcke).

### Mathematik & Chemie (KaTeX, synchron)

- KaTeX als **marked-Extension** (Tokenizer) — respektiert den Code-Kontext, d. h. Formeln
  in Inline-Code/```-Blöcken bleiben Quelltext. Delimiter: `\(…\)`/`\[…\]` und `$…$`/`$$…$$`.
  `throwOnError: false`, damit unvollständige (Streaming) oder fehlerhafte Formeln das
  Rendering nicht brechen.
- **Chemie:** `import 'katex/contrib/mhchem'` registriert `\ce{}`/`\pu{}` (Reaktionsgleichungen).
- **Sicherheit — „protect-and-reinsert":** Die von KaTeX **erzeugte** Ausgabe ist
  vertrauenswürdig (KaTeX parst TeX, schleust kein HTML durch; `trust:false`-Default) und soll
  die strikte Markdown-Sanitisierung nicht aufweichen. Formeln werden vor `marked`+DOMPurify
  durch einen Platzhalter ersetzt und erst **nach** der Sanitisierung wieder eingesetzt —
  DOMPurify bleibt strikt fürs Markdown und zerschießt die KaTeX-Inline-Styles nicht.

### Diagramme (Mermaid, asynchron)

- Mermaid rendert **asynchron** und passt nicht in den synchronen `renderMarkdown`. Der
  Code-Renderer erzeugt für ```mermaid daher nur einen **Platzhalter**
  `<div class="mermaid-block">QUELLE</div>`; die Svelte-Action
  `frontend/src/lib/diagrams.js → renderDiagrams` rendert ihn nach dem Mount im DOM.
- **Lazy:** `import('mermaid')` → eigener (~6 MB) Chunk, erst beim ersten Diagramm geladen.
- `securityLevel: 'strict'`, Theme aus der `dark`-Klasse von `documentElement`. **Debounce
  (250 ms)** gegen Streaming-Flackern (rendert erst, wenn der Inhalt zur Ruhe kommt);
  `data-processed` vor dem `await` gegen Doppel-Render; Fehlerfall → `.mermaid-error` + Quelltext.
- Eingehängt via `use:renderDiagrams` in `MessageBubble` (neben `use:copyButtons`) und
  `knowledge/[id]`.

### Schaltpläne (CircuiTikZ) — bewusst NICHT client-seitig

Elektrische Schaltpläne brauchen eine TeX-Engine (CircuiTikZ); ein Spike + Browser-PoC ergab,
dass es **kein sauberes Browser-npm-Paket mit circuitikz** gibt (`node-tikzjax` kann es, ist
aber reines Node). Entscheidung: **Server-Render in Phase 17** (`node-tikzjax`), gemeinsam mit
dem LaTeX-PDF-Export. Hintergrund: `frontend/scripts/circuit_spike/DECISION.md`.

## Stores (`frontend/src/lib/stores/`)

| Store | Typ | Inhalt |
|-------|-----|--------|
| `user.js` | Svelte writable | `{ pseudonym, roles, grade, display_name, preferences }` |
| `budget.js` | Svelte writable | `{ remaining_eur, max_budget_eur, budget_duration }` |
| `theme.js` | Custom Store | Aktive Theme-Präferenz (`light`/`dark`/`system`) |
| `pageTitle.js` | Svelte writable | Aktueller Seitentitel (für AppHeader) |
| `conversations.js` | Svelte writable | Konversationsliste (History-Sidebar) |

`display_name` im User-Store kommt aus `sessionStorage` — er wird beim
Neuladen der Seite aus `sessionStorage.getItem('display_name')` geladen,
nicht vom Backend.
