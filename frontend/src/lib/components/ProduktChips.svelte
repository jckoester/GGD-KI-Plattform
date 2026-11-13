<script>
    // Angehängte Produkte aus der Werkstatt über dem Eingabefeld (0.41, Schritt 10) — neben
    // den Bausteinen (`ContextChips`), in derselben Form, mit dem Werkstatt-Symbol.
    import { Hammer, X } from "lucide-svelte";
    import { kindLabel } from "$lib/library.js";

    let { produkte = [], onremove, disabled = false } = $props();
</script>

{#if produkte.length > 0}
    <div class="flex flex-wrap gap-1.5">
        {#each produkte as p (p.artifact_id)}
            <span
                class="inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs border
                       border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2
                       bg-light-bg-2 dark:bg-dark-bg-2"
                title="{kindLabel(p.kind)} aus deiner Werkstatt"
            >
                <Hammer class="w-3 h-3 shrink-0" />
                <a href="/workshop/{p.artifact_id}" class="max-w-[200px] truncate hover:underline">{p.title}</a>
                {#if !disabled}
                    <button
                        type="button"
                        onclick={() => onremove?.(p.artifact_id)}
                        class="text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx ml-0.5"
                        title="Aus dem Chat nehmen"
                        aria-label="Produkt {p.title} aus dem Chat nehmen"
                    >
                        <X class="w-3 h-3" />
                    </button>
                {/if}
            </span>
        {/each}
    </div>
{/if}
