<script>
    import { page } from '$app/stores';
    import { getSiteText } from '$lib/api.js';
    import { renderMarkdown } from '$lib/markdown.js';

    const VALID_KEYS = ['impressum', 'datenschutz', 'regeln'];
    const LABELS = {
        impressum: 'Impressum',
        datenschutz: 'Datenschutzerklärung',
        regeln: 'Nutzungsregeln'
    };

    let renderedContent = $state('');
    let error = $state(null);
    let loading = $state(true);

    const schluessel = $derived($page.params.key);

    // Läuft bei jedem Seitenwechsel erneut. Der Zustand wird dabei **zurückgesetzt**:
    // Vorher blieb nach einem unbekannten Schlüssel die Fehlermeldung stehen, und die
    // nächste, gültige Seite zeigte sie weiter — die Vorlage prüft `error` vor dem Inhalt.
    $effect(() => {
        const aktuell = schluessel;
        error = null;
        renderedContent = '';
        if (!VALID_KEYS.includes(aktuell)) {
            error = 'Unbekannte Seite';
            loading = false;
            return;
        }
        loading = true;
        loadText(aktuell);
    });

    async function loadText(key) {
        try {
            const data = await getSiteText(key);
            renderedContent = renderMarkdown(data.content);
        } catch (e) {
            error = e.message || 'Fehler beim Laden';
        } finally {
            loading = false;
        }
    }
</script>

<div class="max-w-2xl mx-auto py-10 px-4">
    <button
        onclick={() => history.back()}
        class="flex items-center gap-1 mb-6 text-sm text-light-tx-2 dark:text-dark-tx-2 
               hover:text-light-tx dark:hover:text-dark-tx transition-colors"
    >
        ← Zurück
    </button>

    {#if loading}
        <div class="text-center py-8">Laden...</div>
    {:else if error}
        <div class="text-center py-8 text-light-re dark:text-dark-re">{error}</div>
    {:else}
        <h1 class="text-2xl font-semibold mb-6 text-light-tx dark:text-dark-tx">
            {LABELS[schluessel] ?? schluessel}
        </h1>
        {#if renderedContent}
            <div class="prose dark:prose-invert max-w-none">
                {@html renderedContent}
            </div>
        {:else}
            <p class="text-light-tx-2 dark:text-dark-tx-2">Kein Inhalt hinterlegt.</p>
        {/if}
    {/if}
</div>
