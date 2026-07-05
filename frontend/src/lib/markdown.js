import { marked } from 'marked';
import DOMPurify from 'dompurify';
import hljs from 'highlight.js/lib/core';
import katex from 'katex';
import 'katex/contrib/mhchem'; // registriert \ce{} und \pu{} (Chemie) auf der katex-Instanz

// Sprachimporte
import javascript from 'highlight.js/lib/languages/javascript';
import typescript from 'highlight.js/lib/languages/typescript';
import python from 'highlight.js/lib/languages/python';
import bash from 'highlight.js/lib/languages/bash';
import sql from 'highlight.js/lib/languages/sql';
import yaml from 'highlight.js/lib/languages/yaml';
import json from 'highlight.js/lib/languages/json';
import css from 'highlight.js/lib/languages/css';
import xml from 'highlight.js/lib/languages/xml';
import markdown from 'highlight.js/lib/languages/markdown';
import plaintext from 'highlight.js/lib/languages/plaintext';

hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('typescript', typescript);
hljs.registerLanguage('python', python);
hljs.registerLanguage('bash', bash);
hljs.registerLanguage('shell', bash); // Alias
hljs.registerLanguage('sql', sql);
hljs.registerLanguage('yaml', yaml);
hljs.registerLanguage('json', json);
hljs.registerLanguage('css', css);
hljs.registerLanguage('xml', xml);
hljs.registerLanguage('html', xml); // Alias
hljs.registerLanguage('markdown', markdown);
hljs.registerLanguage('plaintext', plaintext);

marked.use({ gfm: true, breaks: true });

// Code-Block-Renderer
const renderer = new marked.Renderer();

renderer.link = ({ href, title, text }) => {
    const titleAttr = title ? ` title="${title}"` : '';
    return `<a href="${href}"${titleAttr} target="_blank" rel="noopener noreferrer">${text}</a>`;
};

function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

renderer.code = function({ text, lang }) {
    // Mermaid: synchroner Platzhalter; das async Rendern macht die Svelte-Action
    // `renderDiagrams` (siehe diagrams.js). Quelle als (escaptes) Textinhalt — die
    // Action liest sie via textContent zurück.
    if (lang === 'mermaid') {
        return `<div class="mermaid-block">${escapeHtml(text)}</div>`;
    }
    // Server-Render (Phase 17): synchroner Platzhalter; das async Rendern (POST an
    // /render/circuit) übernimmt die Svelte-Action `renderServerBlocks` (serverRender.js).
    // Quelle als escaptes textContent — die Action liest sie zurück.
    if (lang === 'circuitikz') {
        return `<div class="circuit-block">${escapeHtml(text)}</div>`;
    }
    const language = lang && hljs.getLanguage(lang) ? lang : null;
    const highlighted = language
        ? hljs.highlight(text, { language }).value
        : hljs.highlightAuto(text).value;
    const displayLang = language ?? '';

    return `<div class="code-block" data-lang="${displayLang}">` +
        `<pre><code class="hljs">${highlighted}</code></pre>` +
        `</div>`;
};

marked.use({ renderer });

// ── KaTeX (Mathe + Chemie via mhchem) ───────────────────────────────────────
// Strategie (Plan Phase 15, D2): KaTeX-Ausgabe wird von uns aus der Quell-Notation
// ERZEUGT (vertrauenswürdig, KaTeX rendert TeX in eine feste span/MathML-Struktur,
// `trust:false` per Default → kein \href javascript:). Sie soll die strikte
// DOMPurify-Sanitisierung des Markdowns NICHT aufweichen. Deshalb: marked-Extension
// liefert nur einen Platzhalter, die echte KaTeX-Ausgabe wird erst NACH DOMPurify
// wieder eingesetzt — so bleibt DOMPurify strikt und zerschießt KaTeX-Styles nicht.
//
// Die Extension respektiert über marked den Code-Kontext: Formeln in `…`-Spans und
// ```-Blöcken bleiben Quelltext (wichtig z. B. für `$VAR` in Bash-Snippets).

// Per-Aufruf-Speicher. marked.parse läuft synchron und nicht-reentrant, daher ist
// das modulweite Zurücksetzen am Anfang von renderMarkdown sicher.
let _mathStore = {};
let _mathCount = 0;
let _mathNonce = '';

function renderKatexPlaceholder(tex, display) {
    let html;
    try {
        html = katex.renderToString(tex, {
            displayMode: !!display,
            throwOnError: false, // fehlerhafte/unvollständige Formeln (Streaming!) nicht werfen
            output: 'htmlAndMathml',
        });
    } catch {
        // Sollte mit throwOnError:false praktisch nicht auftreten → Rohtext zurückgeben.
        const d = display ? '$$' : '$';
        return d + tex + d;
    }
    const id = _mathCount++;
    _mathStore[id] = html;
    return `KMATH${_mathNonce}X${id}X`;
}

// Display-Mathe ($$…$$, \[…\]) — auch als Inline-Fallback verwendet.
function matchDisplayMath(src) {
    let m;
    if ((m = /^\$\$([\s\S]+?)\$\$/.exec(src))) return { raw: m[0], text: m[1], display: true };
    if ((m = /^\\\[([\s\S]+?)\\\]/.exec(src))) return { raw: m[0], text: m[1], display: true };
    return null;
}

// Inline-Mathe: Display zuerst, dann \(…\) und $…$.
// $…$-Heuristik gegen Währungs-Fehltreffer (D1): öffnendes $ nicht von Space/$ gefolgt,
// schließendes $ nicht von einer Ziffer gefolgt ($5 … $10 bleibt so Text).
function matchInlineMath(src) {
    const d = matchDisplayMath(src);
    if (d) return d;
    let m;
    if ((m = /^\\\(([\s\S]+?)\\\)/.exec(src))) return { raw: m[0], text: m[1], display: false };
    if ((m = /^\$(?![\s$])((?:\\.|[^$\\\n])+?)\$(?!\d)/.exec(src)))
        return { raw: m[0], text: m[1], display: false };
    return null;
}

const katexBlockExt = {
    name: 'katexBlock',
    level: 'block',
    start(src) {
        const i = src.search(/\$\$|\\\[/);
        return i < 0 ? undefined : i;
    },
    tokenizer(src) {
        const t = matchDisplayMath(src);
        if (t) return { type: 'katexBlock', raw: t.raw, text: t.text, display: t.display };
    },
    renderer(token) {
        return renderKatexPlaceholder(token.text, token.display);
    },
};

const katexInlineExt = {
    name: 'katexInline',
    level: 'inline',
    start(src) {
        const i = src.search(/\$|\\[([]/);
        return i < 0 ? undefined : i;
    },
    tokenizer(src) {
        const t = matchInlineMath(src);
        if (t) return { type: 'katexInline', raw: t.raw, text: t.text, display: t.display };
    },
    renderer(token) {
        return renderKatexPlaceholder(token.text, token.display);
    },
};

marked.use({ extensions: [katexBlockExt, katexInlineExt] });

export function renderMarkdown(text) {
    if (!text) return '';
    // Per-Aufruf-Speicher zurücksetzen; Nonce verhindert Kollision mit echtem Inhalt.
    _mathStore = {};
    _mathCount = 0;
    _mathNonce = Math.random().toString(36).slice(2, 10);

    const clean = DOMPurify.sanitize(marked.parse(text), {
        ADD_TAGS: ['div'],
        ADD_ATTR: ['data-lang', 'class', 'target', 'rel'],
    });

    if (_mathCount === 0) return clean;
    // Platzhalter durch die (vertrauenswürdige) KaTeX-Ausgabe ersetzen.
    return clean.replace(
        new RegExp(`KMATH${_mathNonce}X(\\d+)X`, 'g'),
        (_, id) => _mathStore[id] ?? '',
    );
}
