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

## Seitenrahmen: `PageBody`

Jede Seite unter `(app)` bekommt ihren Rahmen von `$lib/components/PageBody.svelte` —
zwei Muster, eine Stelle:

```svelte
<PageBody breit>   <!-- Listen über die volle Breite (Vorbild /knowledge) -->
<PageBody>         <!-- Detail, Editoren, gruppierte Listen (Vorbild /knowledge/mine) -->
```

⚠️ **Der Scroll-Rahmen ist Pflicht.** Das `(app)`-Layout gibt `<main>` ein
`flex-1 overflow-hidden`; eine Seite ohne `h-full overflow-y-auto` wird unten
**abgeschnitten**, statt zu scrollen. Der Fehler sieht nicht kaputt aus — er fällt erst
auf, wenn der Inhalt lang wird, und ist mehrfach passiert. In der Komponente kann er
einer Seite nicht mehr unterlaufen.

**Wann breit, wann schmal?** Listen und Tabellen brauchen den Platz — alles, was gelesen
oder ausgefüllt wird, nicht. Eine Textspalte am linken Rand eines breiten Schirms ist
unangenehm zu lesen, deshalb zentriert die schmale Variante (`max-w-4xl mx-auto`).

**Ausnahmen — Seiten mit eigener Flex-Struktur.** Chat, Graph, Suche, Curriculum-Ansicht
und -Editor, Planer, Werkstatt und der Assistenten-Editor verwalten ihren
Scrollbereich selbst; sie haben feste Kopf- oder Fußleisten, die nicht mitscrollen
dürfen. Dort gilt `PageBody` **nicht** — wohl aber dieselbe Inhaltsbreite: `max-w-4xl
mx-auto w-full` für Lesbares, volle Breite für Tabellen und Zeichenflächen.

> **Der `(admin)`-Bereich hat einen anderen Rahmenvertrag.** Dort scrollt das *Layout*
> (`<main class="flex-1 overflow-y-auto px-4 py-4">`), nicht die Seite. `PageBody` würde
> einen zweiten Scrollbereich hineinschieben und gehört deshalb nicht dorthin.

**Die `help/*`-Seiten bleiben bei `max-w-2xl`** — sie sind Fließtext, und für den ist die
schmalere Spalte die bessere Lesbreite. Sie sind untereinander einheitlich.

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

## Rich-Rendering im Markdown (KaTeX, Mermaid/Pele)

Ein **zentraler** Renderer `frontend/src/lib/markdown.js` (`renderMarkdown`) speist Chat
(`MessageBubble`), Bibliothek (`/knowledge/[id]`), Curriculum-Tabelle und Hilfeseiten —
eine Erweiterung dort wirkt überall. Pipeline: `marked` → `DOMPurify.sanitize`
(+ highlight.js für Codeblöcke).

### Mathematik & Chemie (KaTeX, synchron)

- KaTeX als **marked-Extension** (Tokenizer) — respektiert den Code-Kontext, d. h. Formeln
  in Inline-Code/```-Blöcken bleiben Quelltext. Delimiter: `\(…\)`/`\[…\]` und `$…$`/`$$…$$`.
  Eine Formel, die KaTeX nicht versteht (`ParseError`), bricht das Rendering nicht, sondern
  wird zur Fehleranzeige (seit 0.30): abgesetzt „Formel nicht darstellbar“ mit der Quelle in
  einem zugeklappten `<details class="formel-fehler">`, im Fließtext die Quelle als
  `<code class="formel-fehler">` mit der Meldung im `title`. Unvollständige Formeln beim
  Streamen erreichen KaTeX gar nicht — die Tokenizer greifen erst beim schließenden Delimiter.
  `renderInlineMath` (Titel) bleibt bei `throwOnError: false`.
- **Chemie:** `import 'katex/contrib/mhchem'` registriert `\ce{}`/`\pu{}` (Reaktionsgleichungen).
- **Sicherheit — „protect-and-reinsert":** Die von KaTeX **erzeugte** Ausgabe ist
  vertrauenswürdig (KaTeX parst TeX, schleust kein HTML durch; `trust:false`-Default) und soll
  die strikte Markdown-Sanitisierung nicht aufweichen. Formeln werden vor `marked`+DOMPurify
  durch einen Platzhalter ersetzt und erst **nach** der Sanitisierung wieder eingesetzt —
  DOMPurify bleibt strikt fürs Markdown und zerschießt die KaTeX-Inline-Styles nicht.

### Formeln eingeben (MathLive, seit 0.38)

- **Eigene Nachrichten** zeigen Formeln gesetzt: `MessageBubble` rendert den Text der
  Nutzer:in mit `renderInlineMath` (Formeln über KaTeX, alles andere escapet, kein Markdown).
  Begrenzer und Währungsschutz wie bei den Antworten.
- **Formel-Dialog** (`FormelDialog.svelte`, Σ-Knopf neben dem Eingabefeld): MathLive
  (`<math-field>`) liefert LaTeX; die Nachricht bleibt Text. Die Logik liegt testbar außerhalb
  der Komponente:
  - `formel.js`: `formelAmCursor` (welche Formel steht am Cursor — gleiche Begrenzer wie
    `markdown.js`), `formelEinsetzen` (setzt `\(…\)` bzw. `\[…\]`, ersetzt oder entfernt),
    `bereinigeLatex` (Platzhalter raus, MathLive-Befehle ohne KaTeX-Gegenstück ersetzen).
  - `formel_editor.js`: `mathliveLaden` (einmal, per `import('mathlive')` — eigener Chunk,
    rund 230 KB gzip, erst beim ersten Öffnen), `einstellen`, `feldEinrichten`,
    `tottasteAbfangen`.
- **Ausgabe:** `getValue('latex-expanded')` statt `latex` — das löst `\exponentialE`,
  `\imaginaryI`, `\differentialD` auf. Was danach noch fehlt, ersetzt `bereinigeLatex`; die
  Vorschau (`formelVorschau` in `markdown.js`, `throwOnError: true`) zeigt, ob KaTeX die
  Formel setzt, und sperrt sonst „Einfügen“.
- ⚠️ **Keine Anfragen nach außen:** MathLive lädt Schriften und Klänge relativ zum eigenen
  Skript. `einstellen` setzt `fontsDirectory`, `soundsDirectory`, `keypressSound` und
  `plonkSound` auf `null`; die Schriften kommen aus `katex.min.css` (gleiche Namen). Die
  Adressen `esm.run` und `aws-sdk` stehen in MathLive nur in Fehlermeldungen (Compute Engine
  und Sprachausgabe über Amazon werden nie geladen). Ein Test hält die Einstellungen fest.
- ⚠️ **Tottasten (`^` auf deutscher Tastatur) in Chrome:** Chrome meldet `keydown key="Dead"`
  vor der Zusammensetzung. MathLive leitet daraus über den Tastencode ein Zeichen ab
  (`IntlBackslash` ist bei US-Belegung `\`), wechselt in den LaTeX-Modus, und aus `^2` wird
  `\^`. Außerdem liefert `compositionend` das `^` samt Folgezeichen (`"^("`), was MathLive
  falsch auswertet. `tottasteAbfangen` hält das Dead-keydown von MathLive fern und gibt
  mehrteilige Zusammensetzungen Zeichen für Zeichen weiter. Safari ist nicht betroffen.
- Escape schaltet in MathLive in den LaTeX-Modus; `feldEinrichten` nimmt die Belegung heraus,
  damit Escape den Dialog schließt. Das Kontextmenü ist auf Ausschneiden, Kopieren,
  Einfügen und Alles auswählen gekürzt.

### Diagramme (Mermaid-Schreibweise, gerendert mit Pele seit 0.36)

- Das Rendern ist **asynchron** (lazy geladen) und passt nicht in den synchronen `renderMarkdown`. Der
  Code-Renderer erzeugt für ```mermaid daher nur einen **Platzhalter**
  `<div class="mermaid-block">QUELLE</div>`; die Svelte-Action
  `frontend/src/lib/diagrams.js → renderDiagrams` rendert ihn nach dem Mount im DOM.
- **Lazy:** `import('pele/lazy')` (`renderAsync`) → kleine Teile je Diagrammtyp, erst beim ersten
  Diagramm geladen.
- Vorher `mermaidReparieren` (`peleHilfen.js`), danach **`sanitizeSvg`** wie bei den
  Server-Diagrammen (Pele schreibt kein `<foreignObject>`); `links: false`, `images: false`.
  **Farben** über `--pele-*` aus den Tokens (`hljs-theme.css`, hell und `.dark`) — der
  Themawechsel braucht kein neues Rendern. Dateien (SVG-Download) bekommen `festeFarben`. **Debounce
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
