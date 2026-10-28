<script>
    /**
     * Assistenten-Vorschlag unter der Antwort (Päckchen C2, 0.24) — eine Rückfrage, keine
     * Automatik. Optionen kommen vom Server (`event: vorschlag`); was eine Wahl bewirkt, steht in
     * `$lib/assistent_vorschlag.js`.
     *
     * Props:
     * - optionen: [{ assistant_id, name, text, art }] — art: specific | fallback | beenden
     * - onWaehlen(option)
     * - onBleiben()
     */
    import { Sparkles } from "lucide-svelte";
    import { beschriftung, einleitung } from "$lib/assistent_vorschlag.js";

    let { optionen = [], onWaehlen, onBleiben } = $props();
    const ueberschriftId = `vorschlag-${Math.random().toString(36).slice(2, 8)}`;
</script>

<section
    aria-labelledby={ueberschriftId}
    class="rounded-lg border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg-2 dark:bg-dark-bg-2
           px-4 py-3 text-sm text-light-tx dark:text-dark-tx"
>
    <h3 id={ueberschriftId} class="flex items-center gap-2 font-medium">
        <Sparkles class="w-4 h-4 text-light-bl dark:text-dark-bl" aria-hidden="true" />
        {einleitung(optionen)}
    </h3>
    <ul class="mt-2 space-y-1.5">
        {#each optionen as option, i (option.assistant_id)}
            <li>
                <button
                    type="button"
                    onclick={() => onWaehlen?.(option)}
                    class="w-full text-left rounded border px-3 py-2 transition-colors
                           focus:outline-none focus:ring-2 focus:ring-primary
                           {i === 0
                        ? 'border-primary dark:border-primary-dark'
                        : 'border-light-ui-3 dark:border-dark-ui-3'}
                           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
                >
                    <span class="block font-medium text-light-bl dark:text-dark-bl">{beschriftung(option)}</span>
                    {#if option.text}
                        <span class="block text-xs text-light-tx-2 dark:text-dark-tx-2">{option.text}</span>
                    {/if}
                </button>
            </li>
        {/each}
    </ul>
    <button
        type="button"
        onclick={() => onBleiben?.()}
        class="mt-2 text-xs text-light-tx-2 dark:text-dark-tx-2 underline hover:text-light-tx
               dark:hover:text-dark-tx focus:outline-none focus:ring-2 focus:ring-primary rounded"
    >
        Hier bleiben
    </button>
</section>
