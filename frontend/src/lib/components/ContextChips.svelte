<script>
    import { X } from "lucide-svelte";
    import { CATEGORY_COLORS } from "$lib/taxonomy.js";
    import NodeTypeIcon from "./NodeTypeIcon.svelte";

    // Vollständige Tailwind-Klassen müssen literal im Quelltext stehen (kein Purging)
    const CHIP_ACCENT = {
        bl: "border-l-2 border-l-light-bl dark:border-l-dark-bl bg-light-bl/10 dark:bg-dark-bl/10",
        gr: "border-light-gr dark:border-dark-gr",
        or: "border-l-2 border-l-light-or dark:border-l-dark-or bg-light-or/10 dark:bg-dark-or/10",
        pu: "border-l-2 border-l-light-pu dark:border-l-dark-pu bg-light-pu/10 dark:bg-dark-pu/10",
    };

    let { nodes = $bindable([]), onremove, disabled = false } = $props();
</script>

{#if nodes.length > 0}
    <div class="flex flex-wrap gap-1.5">
        {#each nodes as node (node.node_id)}
            {@const colorToken = CATEGORY_COLORS[node.category] ?? ""}
            {@const accentClass = CHIP_ACCENT[colorToken] ?? ""}
            <span
                class="inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs border text-light-tx-2 dark:text-dark-tx-2 bg-light-bg-2 dark:bg-dark-bg-2 {accentClass}"
            >
                {#if node.content_type}
                    <NodeTypeIcon
                        category={node.category}
                        contentType={node.content_type}
                        size={12}
                    />
                {/if}
                <span class="max-w-[200px] truncate" title={node.title}>
                    {node.title}
                </span>
                {#if !disabled}
                    <button
                        type="button"
                        onclick={() => onremove?.(node.node_id)}
                        class="text-light-tx-2 dark:text-dark-tx-2
                               hover:text-light-tx dark:hover:text-dark-tx
                               ml-0.5"
                        title="Aus Kontext entfernen"
                        aria-label="Knoten {node.title} aus Kontext entfernen"
                    >
                        <X class="w-3 h-3" />
                    </button>
                {/if}
            </span>
        {/each}
    </div>
{/if}
