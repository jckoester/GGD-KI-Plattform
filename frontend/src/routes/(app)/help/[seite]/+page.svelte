<script>
    import { renderMarkdown } from '$lib/markdown.js';
    import ErrorBanner from '$lib/components/ErrorBanner.svelte';

    let { data } = $props();

    /**
     * Alle Dokumente auf einmal — `eager`, damit der Wechsel zwischen Hilfeseiten ohne
     * Nachladen auskommt. Es sind kurze Markdown-Dateien, und sie stehen zur Bauzeit
     * ohnehin fest.
     */
    const dokumente = import.meta.glob('$docs/*.md', {
        query: '?raw',
        import: 'default',
        eager: true,
    });

    /**
     * Dateiname ohne Endung → Inhalt.
     *
     * ⚠️ **Nicht über den ganzen Schlüssel.** Vite gibt die Pfade so zurück, wie das
     * Muster sie erzeugt (`../docs/user/chat.md`) — eine Form, die sich mit der
     * Konfiguration ändern kann und gegen die man nicht vergleichen sollte. Der
     * Dateiname ist das, was `help-nav.js` kennt.
     */
    const nachDatei = Object.fromEntries(
        Object.entries(dokumente).map(([pfad, text]) => [
            pfad.split('/').pop().replace(/\.md$/, ''),
            text,
        ]),
    );

    const inhalt = $derived(nachDatei[data.eintrag.file]);
</script>

<!-- Rahmen schmal wie alle Leseseiten (0.48), die Textspalte bleibt auf Lesebreite (G8 a). -->
<div class="max-w-4xl mx-auto px-6 py-6">
    {#if inhalt}
        <div class="prose dark:prose-invert max-w-prose">
            {@html renderMarkdown(inhalt, { dokuLinks: true })}
        </div>
    {:else}
        <!-- Sichtbar scheitern statt leer bleiben: Eine Hilfeseite ohne Text sieht aus
             wie ein Ladefehler und wird nicht gemeldet. Verhindern soll das der Wächter
             `help_nav.test.js` — falls doch etwas durchrutscht, steht es hier. -->
        <ErrorBanner
            message="Zu „{data.eintrag.label}“ fehlt die Datei docs/user/{data.eintrag.file}.md."
        />
    {/if}
</div>
