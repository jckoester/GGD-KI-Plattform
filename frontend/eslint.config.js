// ESLint Flat-Config (ESLint 9+/10). Ersetzt die früheren .eslintrc.*-Dateien.
//
// Bewusst schlank gehalten: geprüft wird auf *Korrektheit* (ungenutzte Variablen,
// Tippfehler in Bezeichnern, Svelte-spezifische Fallstricke), nicht auf Formatierung.
// Layout-Fragen bleiben dem Editor überlassen — sonst erzeugt der erste Lauf über eine
// nie gelintete Codebasis nur Rauschen.
//
// Ausführen: npm run lint

import js from '@eslint/js'
import globals from 'globals'
import svelte from 'eslint-plugin-svelte'
import svelteConfig from './svelte.config.js'

export default [
    {
        ignores: [
            'build/',
            'dist/',
            '.svelte-kit/',
            'node_modules/',
            // Generiert aus backend/app/context/taxonomy.yaml (npm run generate:taxonomy) — nicht handgepflegt.
            'src/lib/taxonomy.js',
        ],
    },

    js.configs.recommended,
    ...svelte.configs.recommended,

    {
        languageOptions: {
            ecmaVersion: 2023,
            sourceType: 'module',
            globals: {
                ...globals.browser,
                ...globals.node,
                // Von Vite zur Build-Zeit ersetzt (vite.config.js → define).
                __APP_VERSION__: 'readonly',
                __GIT_COMMIT__: 'readonly',
            },
        },
        rules: {
            // Ungenutzte Funktionsargumente sind in Callbacks/Event-Handlern normal;
            // ein führender Unterstrich markiert sie als absichtlich ungenutzt.
            'no-unused-vars': [
                'error',
                { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrors: 'none' },
            ],
            // `catch {}` ist im SSE-Parser (api.js) die bewusste Reaktion auf einen
            // fehlerhaften Payload: Event überspringen, Stream weiterlaufen lassen.
            'no-empty': ['error', { allowEmptyCatch: true }],
            // Geschützte Leerzeichen (U+00A0) in Template-Strings sind deutsche
            // Typografie („KW 12", „3. Std"), kein Versehen.
            'no-irregular-whitespace': ['error', { skipTemplates: true }],
        },
    },

    {
        // Der Svelte-Parser braucht die Projekt-Config, um Runes und Preprocessing
        // korrekt aufzulösen (Svelte 5).
        files: ['**/*.svelte', '**/*.svelte.js'],
        languageOptions: {
            parserOptions: { svelteConfig },
        },
        rules: {
            // AUS — passt nicht zu diesem Projekt:
            //
            // Die Regel verlangt `resolve()` um jedes href/goto. Das ist nur nötig, wenn
            // die App unter einem `base`-Pfad läuft; svelte.config.js setzt keinen
            // (Auslieferung an der Wurzel hinter nginx). Wieder einschalten, falls
            // jemals `kit.paths.base` gesetzt wird.
            'svelte/no-navigation-without-resolve': 'off',
            // Verlangt SvelteMap/SvelteSet/SvelteDate statt Map/Set/Date. Nur relevant,
            // wenn der Wert reaktiv sein *soll* — die Treffer hier sind lokale Helfer.
            'svelte/prefer-svelte-reactivity': 'off',

            // WARNUNG statt Fehler — real, aber je ein eigenes Vorhaben:
            //
            // `{@html}` wird hier ausschließlich mit vorher DOMPurify-saniertem HTML
            // benutzt (markdown.js, sanitizeSvg). Sichtbar halten, damit ein künftiger
            // ungesicherter Einsatz auffällt, aber nicht blockierend.
            'svelte/no-at-html-tags': 'warn',
            // Gekeyte {#each} sind korrekt, wenn Listen umsortiert werden oder Einträge
            // eigenen Zustand haben. Nachziehen lohnt, ist aber ein eigener Umbau.
            'svelte/require-each-key': 'warn',
            // Heuristik; die Treffer stammen aus einer Datei mit Svelte-4-`$:`-Blöcken
            // (src/routes/info/[key]). Verschwindet mit der Migration auf Runes.
            'svelte/infinite-reactive-loop': 'warn',
        },
    },
]
