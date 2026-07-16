<script>
    import { goto } from '$app/navigation'
    import { page } from '$app/stores'
    import { user, userHasAnyRole } from '$lib/stores/user.js'
    import { getContextNodes } from '$lib/api.js'
    import NodeTypeIcon from '$lib/components/NodeTypeIcon.svelte'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import LfdbTree from '$lib/components/LfdbTree.svelte'
    import { ArrowLeft, TriangleAlert, ChevronDown, ChevronRight, ExternalLink } from 'lucide-svelte'

    // Auth-Prüfung: nur teacher/admin
    $effect(() => {
        if ($page.url.pathname.startsWith('/knowledge/cross-cutting-themes') && $user && !userHasAnyRole($user, ['teacher', 'admin'])) {
            goto('/chat')
        }
    })

    let nodes = $state([])
    let loading = $state(true)
    let error = $state(null)

    // Lade Leitperspektiven und ihre Aspekte
    $effect(() => {
        loadLeitperspektiven()
    })

    async function loadLeitperspektiven() {
        loading = true
        error = null
        try {
            const data = await getContextNodes({
                content_type: [
                    'leitperspektive', 'leitperspektive_aspekt',
                    'lfdb_baustein', 'lfdb_themenblock', 'lfdb_kompetenz',
                ]
            })
            // getContextNodes liefert ein Array (response_model=list[...]),
            // kein {items}-Objekt.
            nodes = data || []
        } catch (e) {
            error = e.message || 'Fehler beim Laden der Leitperspektiven'
        } finally {
            loading = false
        }
    }

    // Gruppe nach Typ
    const groupedNodes = $derived({
        leitperspektiven: nodes.filter(n => n.content_type === 'leitperspektive'),
        aspekte: nodes.filter(n => n.content_type === 'leitperspektive_aspekt')
    })

    // Ordne Aspekte ihren Leitperspektiven zu
    const leitperspektivenWithAspekte = $derived(groupedNodes.leitperspektiven.map(lp => ({
        ...lp,
        aspekte: groupedNodes.aspekte.filter(a => a.metadata?.kuerzel === lp.metadata?.kuerzel)
    })))

    // LFDB: 3-Ebenen-Baum (Baustein → Themenblock → Kompetenz) aus den bp_ids ableiten.
    // bp_id-Schema: …_LFDB_B<n> / …_B<n>_T<t> / …_B<n>_T<t>_K<k>; die _T/_K-Trenner
    // verhindern Präfix-Kollisionen (B1 vs B10).
    const _bpid = (n) => n.metadata?.bp_id ?? ''
    const _numcmp = (a, b) => _bpid(a).localeCompare(_bpid(b), undefined, { numeric: true })
    const lfdbTree = $derived(
        nodes.filter(n => n.content_type === 'lfdb_baustein').sort(_numcmp).map(b => ({
            ...b,
            themenbloecke: nodes
                .filter(t => t.content_type === 'lfdb_themenblock' && _bpid(t).startsWith(_bpid(b) + '_T'))
                .sort(_numcmp)
                .map(t => ({
                    ...t,
                    kompetenzen: nodes
                        .filter(k => k.content_type === 'lfdb_kompetenz' && _bpid(k).startsWith(_bpid(t) + '_K'))
                        .sort(_numcmp),
                })),
        }))
    )
    const isLfdb = (lp) => lp.metadata?.kuerzel === 'LFDB'

    // Einklapp-Zustand der Leitperspektiven (analog Leitideen im Fachplan,
    // standardmäßig eingeklappt für eine kompakte Übersicht)
    let expandedLPs = $state({})
    function toggleLP(id) {
        expandedLPs = { ...expandedLPs, [id]: !expandedLPs[id] }
    }

    // Navigationsfunktion
    function navigateToNode(nodeId) {
        goto(nodeHref(nodeId))
    }

    function nodeHref(nodeId) {
        return `/knowledge/${nodeId}?back=${encodeURIComponent($page.url.pathname)}`
    }
</script>

<div class="h-full overflow-y-auto p-6 max-w-4xl">
        <!-- Kopfzeile -->
        <div class="flex items-center justify-between mb-6">
            <div>
                <a
                    href="/knowledge"
                    class="flex items-center gap-1 mb-2 text-sm text-light-tx-2 dark:text-dark-tx-2
                         hover:text-light-tx dark:hover:text-dark-tx transition-colors"
                >
                    <ArrowLeft class="w-4 h-4" /> Zurück zu Wissensdatenbank
                </a>
                <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">
                    Leitperspektiven
                </h1>
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
                    Schulübergreifende Themen und Kompetenzen
                </p>
            </div>
        </div>

        <!-- Lade-Indikator -->
        {#if loading}
            <LoadingBanner message="Leitperspektiven werden geladen…" />
        {:else if error}
            <ErrorBanner message={error} />
        {:else if leitperspektivenWithAspekte.length === 0}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                Keine Leitperspektiven verfügbar.
            </p>
        {:else}
            <!-- Leitperspektiven-Liste -->
            <div class="space-y-4">
                {#each leitperspektivenWithAspekte as lp (lp.id)}
                    <div class="bg-light-bg-2 dark:bg-dark-bg-2 rounded-lg border 
                                border-light-ui-3 dark:border-dark-ui-3 overflow-hidden">
                        <!-- Leitperspektive Header (Toggle, analog Leitideen) -->
                        <div
                            class="w-full flex items-center justify-between gap-3
                                   bg-light-bg-3 dark:bg-dark-bg-3
                                   hover:bg-light-bg-4 dark:hover:bg-dark-bg-4 transition-colors"
                        >
                            <div class="flex items-center gap-2 min-w-0 pl-4">
                                <button
                                    onclick={() => toggleLP(lp.id)}
                                    class="flex items-center gap-3 min-w-0 py-4 text-left
                                           text-light-tx dark:text-dark-tx"
                                >
                                    <NodeTypeIcon contentType="leitperspektive" size={20} />
                                    <span class="font-medium truncate">{lp.title}</span>
                                </button>
                                <a
                                    href={nodeHref(lp.id)}
                                    title="Knotenansicht öffnen"
                                    class="shrink-0 p-1 rounded text-light-tx-2 dark:text-dark-tx-2
                                           hover:text-primary dark:hover:text-dark-bl transition-colors"
                                >
                                    <ExternalLink class="w-4 h-4" />
                                </a>
                            </div>
                            <button
                                onclick={() => toggleLP(lp.id)}
                                class="flex items-center gap-2 py-4 pr-4 pl-2 shrink-0
                                       text-light-tx dark:text-dark-tx"
                            >
                                <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                                    {isLfdb(lp) ? `${lfdbTree.length} Bausteine` : `${lp.aspekte.length} Aspekte`}
                                </span>
                                {#if expandedLPs[lp.id]}
                                    <ChevronDown class="w-4 h-4 shrink-0" />
                                {:else}
                                    <ChevronRight class="w-4 h-4 shrink-0" />
                                {/if}
                            </button>
                        </div>

                        <!-- Import-Hinweis (z. B. LFDB — Inhalte nur als PDF) -->
                        {#if lp.metadata?.import_hinweis}
                            <div class="flex items-start gap-2 px-4 py-3 border-t border-light-ui-3 dark:border-dark-ui-3
                                        text-sm text-light-tx-2 dark:text-dark-tx-2">
                                <TriangleAlert class="w-4 h-4 shrink-0 mt-0.5 text-light-ye dark:text-dark-ye" />
                                <span>{lp.metadata.import_hinweis}</span>
                            </div>
                        {/if}

                        <!-- Aufgeklappter Inhalt: LFDB → 3-Ebenen-Baum, sonst flache Aspekte -->
                        {#if expandedLPs[lp.id]}
                            {#if isLfdb(lp)}
                                <LfdbTree bausteine={lfdbTree} {nodeHref} />
                            {:else if lp.aspekte.length > 0}
                                <div class="p-3 space-y-2 border-t border-light-ui-3 dark:border-dark-ui-3">
                                    {#each lp.aspekte as aspekt (aspekt.id)}
                                        <button
                                            onclick={() => navigateToNode(aspekt.id)}
                                            class="w-full flex items-center gap-3 p-2 rounded hover:bg-light-bg-3 dark:hover:bg-dark-bg-3
                                                   text-light-tx dark:text-dark-tx text-sm transition-colors text-left"
                                        >
                                            <NodeTypeIcon contentType="leitperspektive_aspekt" size={16} />
                                            <span class="flex-1">{aspekt.title}</span>
                                        </button>
                                    {/each}
                                </div>
                            {/if}
                        {/if}
                    </div>
                {/each}
            </div>
        {/if}
</div>
