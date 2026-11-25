<script>
    /**
     * Eine Zeile in den Fachlisten der Bibliothek: Curricula (seit 0.46) und Jahresverlaufspläne
     * (seit 0.59, BD Schritt 7) — derselbe Rahmen, dieselben Marken.
     *
     * Props:
     * - `href`, `titel`, `zusatz` (grauer Text hinter dem Titel)
     * - `entwurf`: Marke „Entwurf“, mit `entwurfHinweis` als Tooltip
     * - `bearbeitbar`: Marke „Bearbeitbar“
     */
    let { href, titel, zusatz = '', entwurf = false, entwurfHinweis = '', bearbeitbar = false } = $props()
</script>

<a
    {href}
    class="flex items-center justify-between gap-2 px-3 py-2 rounded-md border border-light-ui-3 dark:border-dark-ui-3
       hover:border-primary dark:hover:border-primary-dark hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
       transition-colors"
>
    <div class="flex-1 min-w-0">
        <span class="font-medium text-light-tx dark:text-dark-tx">{titel}</span>
        {#if zusatz}<span class="text-sm text-light-tx-2 dark:text-dark-tx-2">{zusatz}</span>{/if}
    </div>
    {#if entwurf}
        <span
            class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium
                   bg-light-ye/20 dark:bg-dark-ye/20 text-light-ye dark:text-dark-ye"
            title={entwurfHinweis || undefined}
        >
            Entwurf
        </span>
    {/if}
    {#if bearbeitbar}
        <span
            class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium
                   bg-light-bl/20 dark:bg-dark-bl/20 text-light-bl dark:text-dark-bl"
        >
            Bearbeitbar
        </span>
    {/if}
</a>
