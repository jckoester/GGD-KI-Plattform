<script>
    import { X } from 'lucide-svelte';

    let {
        nodes = $bindable([]),
        onremove,
        disabled = false,
    } = $props();
</script>

{#if nodes.length > 0}
    <div class="flex flex-wrap gap-1.5">
        {#each nodes as node (node.node_id)}
            <span
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs
                       bg-light-ui dark:bg-dark-ui
                       border border-light-ui-3 dark:border-dark-ui-3
                       text-light-tx dark:text-dark-tx"
            >
                {#if node.content_type}
                    <span class="text-light-tx-2 dark:text-dark-tx-2 font-mono text-[10px]">
                        {node.content_type}
                    </span>
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
