/**
 * Symbole der Fächer (`icon:` in `config/subjects.yaml`), je Symbol nachgeladen (0.50).
 *
 * Die Namen stehen frei in der Konfiguration der Schule, deshalb gibt es keine feste Liste.
 * Bis 0.50 lud `SubjectIcon.svelte` dafür mit `import('lucide-svelte')` die **ganze**
 * Bibliothek — ein Chunk von 6 MB beim ersten Aufruf einer Seite mit Fach-Symbol. Jetzt ist
 * jedes Symbol ein eigener, kleiner Chunk; geladen wird nur, was angezeigt wird.
 *
 * Die `.js`-Dateien unter `dist/icons` decken auch die Aliasse ab (`code-2` → `code-xml`).
 */
const SYMBOLE = import.meta.glob('/node_modules/lucide-svelte/dist/icons/*.js')

const PFAD = '/node_modules/lucide-svelte/dist/icons/'

/**
 * Lader für ein Symbol in kebab-case, oder `null`, wenn es das Symbol nicht gibt.
 * @param {string | null | undefined} name
 * @returns {(() => Promise<{default: any}>) | null}
 */
export function symbolLader(name) {
    if (!name || !/^[a-z0-9-]+$/.test(name)) return null
    return SYMBOLE[`${PFAD}${name}.js`] ?? null
}
