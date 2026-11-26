<script>
    import { X } from "@lucide/svelte";
    import { CATEGORY_COLORS } from "$lib/taxonomy.js";
    import { mehrdeutigeFassungen } from "$lib/bp_fassung.js";
    import ContextNodeLabel from "./ContextNodeLabel.svelte";
    import { CHIP_AKZENT, CHIP_FORM, CHIP_ICON } from "$lib/chip_form.js";

    let { nodes = $bindable([]), onremove, disabled = false } = $props();

    // Zwei angeheftete Kompetenzen gleicher Nummer aus verschiedenen Fassungen
    // wären sonst zwei identisch beschriftete Pillen.
    const fassungen = $derived(mehrdeutigeFassungen(nodes));
</script>

<!-- Nur die Chips, ohne eigenen Rahmen: Sie stehen mit Produkten und Anhängen in einer Reihe,
     die `NachrichtenChips` einklappt (0.49). -->
{#each nodes as node (node.node_id)}
    {@const colorToken = CATEGORY_COLORS[node.category] ?? ""}
    {@const accentClass = CHIP_AKZENT[colorToken] ?? CHIP_AKZENT.bl}
    <span class="{CHIP_FORM} {accentClass}">
        <ContextNodeLabel
            {node}
            fassung={fassungen.get(node.node_id)}
            iconSize={CHIP_ICON}
            titleClass="max-w-[200px] truncate"
        />
        {#if !disabled}
            <button
                type="button"
                onclick={() => onremove?.(node.node_id)}
                class="text-light-tx-2 dark:text-dark-tx-2
                       hover:text-light-tx dark:hover:text-dark-tx
                       ml-0.5"
                title="Aus Kontext entfernen"
                aria-label="Baustein {node.title} aus Kontext entfernen"
            >
                <X class="w-3 h-3" />
            </button>
        {/if}
    </span>
{/each}
