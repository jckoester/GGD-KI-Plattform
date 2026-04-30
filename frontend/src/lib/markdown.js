import { marked } from 'marked';
import DOMPurify from 'dompurify';
import hljs from 'highlight.js/lib/core';

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

renderer.code = function({ text, lang }) {
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

export function renderMarkdown(text) {
    if (!text) return '';
    return DOMPurify.sanitize(marked.parse(text), {
        ADD_TAGS: ['div'],
        ADD_ATTR: ['data-lang', 'class', 'target', 'rel'],
    });
}
