<script>
    import NodeTypeIcon from "./NodeTypeIcon.svelte";

    let { nodes = [], onconfirm, ondismiss } = $props();

    let selected = $state(new Set(nodes.map((n) => n.node_id)));

    function toggle(node_id) {
        const next = new Set(selected);
        if (next.has(node_id)) {
            next.delete(node_id);
        } else {
            next.add(node_id);
        }
        selected = next;
    }

    function confirm() {
        onconfirm?.(nodes.filter((n) => selected.has(n.node_id)));
    }
</script>

<div
    class="rounded-lg border border-light-ui-3 dark:border-dark-ui-3
           bg-light-bg-2 dark:bg-dark-bg-2 p-3 text-sm"
>
    <p class="text-xs font-medium text-light-tx-2 dark:text-dark-tx-2 mb-2">
        Passende Wissensknoten gefunden — zum Kontext hinzufügen?
    </p>
    <ul class="flex flex-col gap-1 mb-3">
        {#each nodes as node (node.node_id)}
            <li>
                <label class="flex items-center gap-2 cursor-pointer">
                    <input
                        type="checkbox"
                        checked={selected.has(node.node_id)}
                        onchange={() => toggle(node.node_id)}
                        class="accent-primary"
                    />
                    {#if node.content_type}
                        <NodeTypeIcon
                            category={node.category}
                            contentType={node.content_type}
                            size={14}
                        />
                    {/if}
                    <span class="truncate text-light-tx dark:text-dark-tx">
                        {node.title}
                    </span>
                </label>
            </li>
        {/each}
    </ul>
    <div class="flex gap-2 justify-end">
        <button
            type="button"
            onclick={ondismiss}
            class="px-3 py-1 rounded text-xs
                   text-light-tx-2 dark:text-dark-tx-2
                   hover:bg-light-ui dark:hover:bg-dark-ui
                   border border-light-ui-3 dark:border-dark-ui-3"
        >
            Abbrechen
        </button>
        <button
            type="button"
            onclick={confirm}
            disabled={selected.size === 0}
            class="px-3 py-1 rounded text-xs
                   bg-primary text-white
                   hover:opacity-90
                   disabled:opacity-40 disabled:cursor-not-allowed"
        >
            Hinzufügen ({selected.size})
        </button>
    </div>
</div>
