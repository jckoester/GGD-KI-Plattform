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
