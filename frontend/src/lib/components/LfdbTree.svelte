<script>
    import NodeTypeIcon from "$lib/components/NodeTypeIcon.svelte";
    import { ChevronDown, ChevronRight, ExternalLink } from "lucide-svelte";

    // bausteine: [{ ...node, themenbloecke: [{ ...node, kompetenzen: [node] }] }]
    let { bausteine = [], nodeHref } = $props();

    let expandedB = $state({});
    let expandedT = $state({});
    const toggleB = (id) => (expandedB = { ...expandedB, [id]: !expandedB[id] });
    const toggleT = (id) => (expandedT = { ...expandedT, [id]: !expandedT[id] });
</script>

<div class="p-3 space-y-2 border-t border-light-ui-3 dark:border-dark-ui-3">
    {#each bausteine as b (b.id)}
        <div class="rounded-md border border-light-ui-3 dark:border-dark-ui-3 overflow-hidden">
            <!-- Baustein -->
            <div class="flex items-center justify-between gap-2 bg-light-bg-3 dark:bg-dark-bg-3">
                <button
                    onclick={() => toggleB(b.id)}
                    class="flex items-center gap-2 min-w-0 py-2.5 pl-3 text-left text-light-tx dark:text-dark-tx"
                >
                    <NodeTypeIcon contentType="lfdb_baustein" size={18} />
                    <span class="font-medium truncate">{b.title}</span>
                </button>
                <button
                    onclick={() => toggleB(b.id)}
                    class="flex items-center gap-2 py-2.5 pr-3 pl-2 shrink-0 text-light-tx dark:text-dark-tx"
                >
                    <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                        {b.themenbloecke.length} Themenblöcke
                    </span>
                    {#if expandedB[b.id]}<ChevronDown class="w-4 h-4" />{:else}<ChevronRight class="w-4 h-4" />{/if}
                </button>
            </div>

            {#if expandedB[b.id]}
                <div class="p-2 space-y-2 border-t border-light-ui-3 dark:border-dark-ui-3">
                    {#each b.themenbloecke as t (t.id)}
                        <div class="rounded border border-light-ui-3 dark:border-dark-ui-3 overflow-hidden">
                            <!-- Themenblock -->
                            <div class="flex items-center justify-between gap-2 bg-light-bg-2 dark:bg-dark-bg-2">
                                <button
                                    onclick={() => toggleT(t.id)}
                                    class="flex items-center gap-2 min-w-0 py-2 pl-3 text-left text-light-tx dark:text-dark-tx"
                                >
                                    <NodeTypeIcon contentType="lfdb_themenblock" size={16} />
                                    <span class="truncate">{t.title}</span>
                                    {#each t.metadata?.leitperspektiven ?? [] as lp}
                                        <span
                                            class="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full
                                                   bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx-2 dark:text-dark-tx-2"
                                        >{lp}</span>
                                    {/each}
                                </button>
                                <button
                                    onclick={() => toggleT(t.id)}
                                    class="flex items-center gap-2 py-2 pr-3 pl-2 shrink-0 text-light-tx dark:text-dark-tx"
                                >
                                    <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                                        {t.kompetenzen.length}
                                    </span>
                                    {#if expandedT[t.id]}<ChevronDown class="w-4 h-4" />{:else}<ChevronRight class="w-4 h-4" />{/if}
                                </button>
                            </div>

                            {#if expandedT[t.id]}
                                <div class="p-2 space-y-1 border-t border-light-ui-3 dark:border-dark-ui-3">
                                    {#each t.kompetenzen as k (k.id)}
                                        <a
                                            href={nodeHref(k.id)}
                                            class="flex items-center gap-2 p-2 rounded hover:bg-light-bg-3 dark:hover:bg-dark-bg-3
                                                   text-light-tx dark:text-dark-tx text-sm transition-colors no-underline"
                                        >
                                            <NodeTypeIcon contentType="lfdb_kompetenz" size={14} />
                                            <span class="flex-1">{k.title}</span>
                                            <ExternalLink class="w-3.5 h-3.5 shrink-0 text-light-tx-2 dark:text-dark-tx-2" />
                                        </a>
                                    {/each}
                                </div>
                            {/if}
                        </div>
                    {/each}
                </div>
            {/if}
        </div>
    {/each}
</div>
