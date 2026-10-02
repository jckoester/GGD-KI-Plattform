/**
 * Was `/about` unter „Verwendete Bibliotheken" nennt (0.12).
 *
 * Bis 0.12 stand dort eine Auswahl — fünf Einträge fürs Frontend, sieben fürs Backend;
 * KaTeX, Mermaid, DOMPurify, WeasyPrint, Pandoc und andere fehlten. Jetzt alle
 * **direkten** Abhängigkeiten. `bibliotheken.test.js` gleicht sie mit `package.json`,
 * `backend/requirements.txt` und `render-sidecar/package.json` ab: Eine neue
 * Abhängigkeit ohne Eintrag hier macht ihn rot.
 *
 * Nicht hier: transitive Abhängigkeiten. Die stehen in den Lockdateien.
 *
 * `paket` ist der Name in der Paketdatei, `name` der lesbare. Gruppen mit
 * `quelle: null` (eigenständige Programme) gleicht kein Test ab.
 */
export const BIBLIOTHEKEN = [
    {
        gruppe: 'Frontend',
        quelle: 'frontend',
        eintraege: [
            { name: 'Svelte', paket: 'svelte', lizenz: 'MIT' },
            { name: 'SvelteKit', paket: '@sveltejs/kit', lizenz: 'MIT' },
            { name: 'Tailwind CSS', paket: 'tailwindcss', lizenz: 'MIT' },
            { name: 'Chart.js', paket: 'chart.js', lizenz: 'MIT' },
            { name: 'd3-force', paket: 'd3-force', lizenz: 'ISC' },
            { name: 'DOMPurify', paket: 'dompurify', lizenz: 'MPL-2.0 oder Apache-2.0' },
            { name: 'highlight.js', paket: 'highlight.js', lizenz: 'BSD-3-Clause' },
            { name: 'js-yaml', paket: 'js-yaml', lizenz: 'MIT' },
            { name: 'KaTeX', paket: 'katex', lizenz: 'MIT' },
            { name: 'lucide-svelte', paket: 'lucide-svelte', lizenz: 'ISC' },
            { name: 'marked', paket: 'marked', lizenz: 'MIT' },
            { name: 'marked-footnote', paket: 'marked-footnote', lizenz: 'MIT' },
            { name: 'Mermaid', paket: 'mermaid', lizenz: 'MIT' },
        ],
    },
    {
        gruppe: 'Backend',
        quelle: 'backend',
        eintraege: [
            { name: 'FastAPI', paket: 'fastapi', lizenz: 'MIT' },
            { name: 'Uvicorn', paket: 'uvicorn', lizenz: 'BSD-3-Clause' },
            { name: 'Pydantic', paket: 'pydantic', lizenz: 'MIT' },
            { name: 'pydantic-settings', paket: 'pydantic-settings', lizenz: 'MIT' },
            { name: 'SQLAlchemy', paket: 'sqlalchemy', lizenz: 'MIT' },
            { name: 'asyncpg', paket: 'asyncpg', lizenz: 'Apache-2.0' },
            { name: 'psycopg2', paket: 'psycopg2-binary', lizenz: 'LGPL-3.0-or-later (mit OpenSSL-Ausnahme)' },
            { name: 'Alembic', paket: 'alembic', lizenz: 'MIT' },
            { name: 'pgvector (Python)', paket: 'pgvector', lizenz: 'MIT' },
            { name: 'httpx', paket: 'httpx', lizenz: 'BSD-3-Clause' },
            { name: 'python-multipart', paket: 'python-multipart', lizenz: 'Apache-2.0' },
            { name: 'python-dotenv', paket: 'python-dotenv', lizenz: 'BSD-3-Clause' },
            { name: 'PyYAML', paket: 'pyyaml', lizenz: 'MIT' },
            { name: 'python-jose', paket: 'python-jose', lizenz: 'MIT' },
            { name: 'bcrypt', paket: 'bcrypt', lizenz: 'Apache-2.0' },
            { name: 'jsonschema', paket: 'jsonschema', lizenz: 'MIT' },
            { name: 'Jinja2', paket: 'jinja2', lizenz: 'BSD-3-Clause' },
            { name: 'WeasyPrint', paket: 'weasyprint', lizenz: 'BSD-3-Clause' },
            { name: 'markdown-it-py', paket: 'markdown-it-py', lizenz: 'MIT' },
            { name: 'mdit-py-plugins', paket: 'mdit-py-plugins', lizenz: 'MIT' },
            { name: 'pdfminer.six', paket: 'pdfminer.six', lizenz: 'MIT' },
            { name: 'python-docx', paket: 'python-docx', lizenz: 'MIT' },
            { name: 'NumPy', paket: 'numpy', lizenz: 'BSD-3-Clause' },
            { name: 'Matplotlib', paket: 'matplotlib', lizenz: 'Matplotlib-Lizenz (PSF-basiert)' },
            { name: 'Lark', paket: 'lark', lizenz: 'MIT' },
            { name: 'spaCy', paket: 'spacy', lizenz: 'MIT' },
            { name: 'spaCy-Sprachmodell Deutsch (de_core_news_md)', paket: 'de_core_news_md', lizenz: 'MIT' },
        ],
    },
    {
        gruppe: 'Render-Sidecar (Schaltpläne, Formeln im Export)',
        quelle: 'sidecar',
        eintraege: [
            { name: 'node-tikzjax', paket: 'node-tikzjax', lizenz: 'LPPL-1.3c' },
            { name: 'MathJax', paket: 'mathjax-full', lizenz: 'Apache-2.0' },
        ],
    },
    {
        gruppe: 'Eigenständige Programme',
        quelle: null,
        eintraege: [
            { name: 'LiteLLM (Proxy)', lizenz: 'MIT' },
            { name: 'PostgreSQL', lizenz: 'PostgreSQL License' },
            { name: 'pgvector (Datenbankerweiterung)', lizenz: 'PostgreSQL License' },
            { name: 'Pandoc', lizenz: 'GPL-2.0-or-later' },
            { name: 'nginx', lizenz: 'BSD-2-Clause' },
        ],
    },
];
