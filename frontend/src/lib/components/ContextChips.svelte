<script>
    import { ChevronDown, ChevronUp, X } from "lucide-svelte";
    import { CATEGORY_COLORS } from "$lib/taxonomy.js";
    import { mehrdeutigeFassungen } from "$lib/bp_fassung.js";
    import ContextNodeLabel from "./ContextNodeLabel.svelte";

    // Vollständige Tailwind-Klassen müssen literal im Quelltext stehen (kein Purging)
    const CHIP_ACCENT = {
        bl: "border-l-2 border-l-light-bl dark:border-l-dark-bl bg-light-bl/10 dark:bg-dark-bl/10",
        gr: "border-light-gr dark:border-dark-gr",
        or: "border-l-2 border-l-light-or dark:border-l-dark-or bg-light-or/10 dark:bg-dark-or/10",
        pu: "border-l-2 border-l-light-pu dark:border-l-dark-pu bg-light-pu/10 dark:bg-dark-pu/10",
    };

    let { nodes = $bindable([]), onremove, disabled = false } = $props();

    // Zwei angeheftete Kompetenzen gleicher Nummer aus verschiedenen Fassungen
    // wären sonst zwei identisch beschriftete Pillen.
    const fassungen = $derived(mehrdeutigeFassungen(nodes));

    // Die Chips stehen über dem Eingabefeld und schieben es nach unten. Bei
    // Anzeigelimit 30 sind 30 Pillen à 200 px möglich — das wären auf einem Telefon
    // ein Dutzend Zeilen, bevor der erste Buchstabe Platz hat. Also: ein paar zeigen,
    // den Rest auf Wunsch.
    const EINGEKLAPPT_SICHTBAR = 5;

    let offen = $state(false);
    const klappbar = $derived(nodes.length > EINGEKLAPPT_SICHTBAR);
    const sichtbar = $derived(
        klappbar && !offen ? nodes.slice(0, EINGEKLAPPT_SICHTBAR) : nodes,
    );
    const versteckt = $derived(nodes.length - sichtbar.length);
</script>

{#if nodes.length > 0}
    <!-- Ausgeklappt bleibt die Leiste gedeckelt und scrollt selbst, statt den Chat
         hochzuschieben. -->
    <div
        class="flex flex-wrap gap-1.5 {klappbar && offen
            ? 'max-h-[20dvh] overflow-y-auto'
            : ''}"
    >
        {#each sichtbar as node (node.node_id)}
            {@const colorToken = CATEGORY_COLORS[node.category] ?? ""}
            {@const accentClass = CHIP_ACCENT[colorToken] ?? ""}
            <span
                class="inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs border text-light-tx-2 dark:text-dark-tx-2 bg-light-bg-2 dark:bg-dark-bg-2 {accentClass}"
            >
                <ContextNodeLabel
                    {node}
                    fassung={fassungen.get(node.node_id)}
                    iconSize={12}
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
                        aria-label="Knoten {node.title} aus Kontext entfernen"
                    >
                        <X class="w-3 h-3" />
                    </button>
                {/if}
            </span>
        {/each}

        {#if klappbar}
            <button
                type="button"
                onclick={() => (offen = !offen)}
                class="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs
                       border border-light-ui-3 dark:border-dark-ui-3
                       text-light-tx-2 dark:text-dark-tx-2
                       hover:bg-light-ui dark:hover:bg-dark-ui"
                aria-expanded={offen}
            >
                {#if offen}
                    <ChevronUp class="w-3 h-3" /> weniger
                {:else}
                    <ChevronDown class="w-3 h-3" /> {versteckt} weitere
                {/if}
            </button>
        {/if}
    </div>
{/if}
