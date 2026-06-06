<script>
    import { goto } from '$app/navigation'
    import { page } from '$app/stores'
    import { user, userHasAnyRole } from '$lib/stores/user.js'
    import { getContextNodes } from '$lib/api.js'
    import NodeTypeIcon from '$lib/components/NodeTypeIcon.svelte'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import { ArrowLeft } from 'lucide-svelte'

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
                content_type: ['leitperspektive', 'leitperspektive_aspekt']
            })
            nodes = data.items || []
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
        aspekte: groupedNodes.aspekte.filter(a => a.metadata?.part_of === lp.id)
    })))

    // Navigationsfunktion
    function navigateToNode(nodeId) {
        goto(`/knowledge/${nodeId}?back=${encodeURIComponent($page.url.pathname)}`)
    }
</script>

<div class="flex min-h-0 flex-1">
    <main class="flex-1 overflow-y-auto p-6 max-w-4xl">
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
                        <!-- Leitperspektive Header -->
                        <button
                            onclick={() => navigateToNode(lp.id)}
                            class="w-full flex items-center gap-3 p-4 
                                   bg-light-bg-3 dark:bg-dark-bg-3 
                                   text-light-tx dark:text-dark-tx hover:bg-light-bg-4 dark:hover:bg-dark-bg-4
                                   transition-colors text-left"
                        >
                            <NodeTypeIcon contentType="leitperspektive" size={20} />
                            <span class="font-medium">{lp.title}</span>
                            <span class="ml-auto text-xs text-light-tx-2 dark:text-dark-tx-2">
                                {lp.aspekte.length} Aspekte
                            </span>
                        </button>

                        <!-- Aspekte-Liste -->
                        {#if lp.aspekte.length > 0}
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
                    </div>
                {/each}
            </div>
        {/if}
    </main>
</div>
