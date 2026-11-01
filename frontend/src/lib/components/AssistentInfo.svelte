<script>
    /**
     * Kosten und Kontext-Dokumente eines Assistenten — neben seinem Namen im Chat
     * (0.27, Plan Schritt 10: F7′ Kosten im Badge, F9 Info-Knopf für alle).
     *
     * Die Marke („~62 🪙“) steht direkt neben dem Namen; der Info-Knopf klappt auf, was
     * dahinter steckt: Kosten je Nachricht, davon die Dokumente, und welche Dokumente der
     * Assistent bei jeder Nachricht mitbekommt. Dateinamen sind für Schüler:innen unverfänglich
     * und erklären, warum der Assistent etwa mit den Schulwerten rechnet.
     */
    import { Info } from "lucide-svelte";
    import { budget } from "$lib/stores/budget.js";
    import { assistentKosten } from "$lib/modellangaben.js";

    let { assistent } = $props();

    let offen = $state(false);
    const kosten = $derived(
        assistentKosten(assistent, $budget?.eur_usd_rate, $budget?.einheiten_je_euro),
    );
    const dokumente = $derived(assistent?.dokumente ?? []);

    function groesse(bytes) {
        return bytes >= 1024 * 1024
            ? `${(bytes / 1024 / 1024).toLocaleString("de-DE", { maximumFractionDigits: 1 })} MB`
            : `${Math.max(1, Math.round(bytes / 1024))} KB`;
    }
</script>

{#if assistent}
    <span class="relative inline-flex items-center gap-1">
        {#if kosten.marke}
            <span class="text-light-tx-2 dark:text-dark-tx-2" title="Geschätzte Kosten je Nachricht">· {kosten.marke}</span>
        {/if}
        <button
            type="button"
            onclick={() => (offen = !offen)}
            onkeydown={(e) => e.key === "Escape" && (offen = false)}
            aria-expanded={offen}
            aria-label="Was dieser Assistent kennt und kostet"
            title="Was dieser Assistent kennt und kostet"
            class="p-0.5 rounded text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx"
        >
            <Info class="w-3.5 h-3.5" />
        </button>
        {#if offen}
            <div
                role="dialog"
                aria-label="Assistent: Kosten und Dokumente"
                class="absolute bottom-full left-0 mb-2 z-30 w-72 p-3 rounded-lg shadow-lg text-xs
                       bg-light-bg dark:bg-dark-bg border border-light-ui-3 dark:border-dark-ui-3
                       text-light-tx dark:text-dark-tx space-y-2"
            >
                <p>
                    {#if kosten.gesamt}
                        Eine Nachricht kostet etwa <strong>{kosten.gesamt}</strong>{#if kosten.dokumente},
                            davon {kosten.dokumente} für die Dokumente{/if}.
                    {:else}
                        Die Kosten dieses Assistenten sind nicht bekannt.
                    {/if}
                    <span class="text-light-tx-2 dark:text-dark-tx-2">Schätzung; abgerechnet wird nach Verbrauch.</span>
                </p>
                {#if dokumente.length > 0}
                    <div>
                        <p class="font-medium">Der Assistent kennt bei jeder Nachricht:</p>
                        <ul class="mt-1 space-y-0.5">
                            {#each dokumente as d (d.name)}
                                <li class="flex justify-between gap-2">
                                    <span class="truncate">{d.name}</span>
                                    <span class="text-light-tx-2 dark:text-dark-tx-2 shrink-0">{groesse(d.groesse_bytes)}</span>
                                </li>
                            {/each}
                        </ul>
                    </div>
                {:else}
                    <p class="text-light-tx-2 dark:text-dark-tx-2">Keine eigenen Dokumente.</p>
                {/if}
            </div>
        {/if}
    </span>
{/if}
