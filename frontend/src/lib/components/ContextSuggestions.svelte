<script>
    import { mehrdeutigeFassungen } from "$lib/bp_fassung.js";
    import ContextNodeLabel from "./ContextNodeLabel.svelte";

    let { nodes = [], onconfirm, ondismiss } = $props();

    let selected = $state(new Set(nodes.map((n) => n.node_id)));

    // Die Vorschlagssuche kennt keinen Jahrgang, kann also beide Fassungen
    // derselben Kompetenz vorschlagen — dann muss die Fassung dabeistehen.
    const fassungen = $derived(mehrdeutigeFassungen(nodes));

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
                    <ContextNodeLabel
                        {node}
                        fassung={fassungen.get(node.node_id)}
                        titleClass="truncate text-light-tx dark:text-dark-tx"
                    />
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
