<script>
    /**
     * Kopfzeile eines aufklappbaren Bereichs der Seitenleiste (0.48, Päckchen N, F8).
     *
     * Zwei Ziele in einer Zeile: Der Name ist ein Link auf die Seite des Bereichs und füllt
     * die Zeile bis zum Pfeil; der Pfeil ist ein eigener Knopf, der nur auf- und zuklappt.
     * Bis 0.47 waren beides kleine Knöpfe um Text und Symbol, und der Raum dazwischen
     * reagierte nicht — „zuverlässig reagieren nur Text und Pfeil“ (Jan, 03.10.2026).
     *
     * `onnavigate` läuft beim Klick auf den Namen (etwa: Bereich öffnen), die Navigation
     * selbst übernimmt der Link.
     */
    import { ChevronDown, ChevronRight } from 'lucide-svelte';

    let {
        href,
        label,
        offen = false,
        ontoggle,
        onnavigate = undefined,
        aktiv = false,
        aufklappbar = true,
        children,
        rechts = undefined,
    } = $props();
</script>

<div
    class="w-full flex items-stretch rounded-lg text-sm font-medium text-light-tx dark:text-dark-tx
           transition-colors
           {aktiv ? 'bg-light-ui-2 dark:bg-dark-ui-2' : 'hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
>
    <a
        {href}
        onclick={onnavigate}
        aria-current={aktiv ? 'page' : undefined}
        class="flex-1 min-w-0 flex items-center gap-2 pl-3 pr-1 py-2 rounded-l-lg
               {aufklappbar ? '' : 'rounded-r-lg'}"
    >
        {@render children()}
    </a>
    {#if rechts}
        <span class="flex items-center pr-1">{@render rechts()}</span>
    {/if}
    {#if aufklappbar}
        <button
            type="button"
            onclick={ontoggle}
            aria-expanded={offen}
            aria-label={`${label} ${offen ? 'zuklappen' : 'aufklappen'}`}
            class="shrink-0 flex items-center px-2.5 rounded-r-lg
                   text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx
                   hover:bg-light-ui-3/50 dark:hover:bg-dark-ui-3/50 transition-colors"
        >
            {#if offen}
                <ChevronDown class="w-4 h-4" />
            {:else}
                <ChevronRight class="w-4 h-4" />
            {/if}
        </button>
    {/if}
</div>
