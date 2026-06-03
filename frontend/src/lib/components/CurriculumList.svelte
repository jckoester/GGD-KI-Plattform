<script>
    /**
     * Liste der Curricula für ein Fach
     * 
     * Props:
     * - subjectId: ID des Fachs
     * - subjectSlug: Slug des Fachs (für Links)
     * - showNewButton: boolean (Default: true) - Zeigt "Neues Curriculum anlegen" Button
     */
    import { goto } from '$app/navigation'
    import { getCurriculaBySubject } from '$lib/api.js'
    import { user } from '$lib/stores/user.js'
    import { myTeachingGroups } from '$lib/stores/myGroups.js'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    
    let { subjectId = null, subjectSlug = null, showNewButton = true } = $props()
    
    let curricula = $state([])
    let loading = $state(true)
    let error = $state(null)
    
    // Prüfe ob User Mitglied der Fachschaft ist (kann Curricula bearbeiten)
    const canEditSubject = $derived.by(() => {
        if (!subjectId || !$user) return false
        if ($user.roles?.includes('admin')) return true
        if ($user.roles?.includes('teacher')) {
            return $myTeachingGroups.some(g => g.subject_id === subjectId)
        }
        return false
    })
    
    // Lade Curricula beim Mount
    $effect(() => {
        if (subjectId) {
            loadCurricula()
        }
    })
    
    async function loadCurricula() {
        loading = true
        error = null
        try {
            const data = await getCurriculaBySubject(subjectId)
            curricula = data || []
        } catch (e) {
            error = e.message
        } finally {
            loading = false
        }
    }
    
    // Sortiere nach Jahrgangsstufe
    const sortedCurricula = $derived(
        [...curricula].sort((a, b) => {
            const aJg = parseInt(a.metadata?.jahrgangsstufe) || 999
            const bJg = parseInt(b.metadata?.jahrgangsstufe) || 999
            return aJg - bJg
        })
    )
    
    // Formatiere Jahrgangsstufe
    function formatJahrgangsstufe(jg) {
        if (!jg) return '?'
        return `Klasse ${jg}`
    }
</script>

<div class="space-y-4">
    <!-- Fehler -->
    {#if error}
        <ErrorBanner message={error} />
    {/if}
    
    <!-- Ladeindikator -->
    {#if loading}
        <LoadingBanner message="Curricula werden geladen…" />
    {:else if sortedCurricula.length === 0}
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
            Keine Curricula für dieses Fach verfügbar.
        </p>
    {:else}
        <!-- Curricula-Liste -->
        <div class="space-y-3">
            {#each sortedCurricula as curr (curr.id)}
                <a
                    href={`/knowledge/curriculum/${curr.id}`}
                    onclick={(e) => { e.preventDefault(); goto(`/knowledge/curriculum/${curr.id}`) }}
                    class="flex items-center justify-between p-4 rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                       hover:border-primary dark:hover:border-primary-dark hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                       transition-colors group"
                >
                    <div class="flex-1 min-w-0">
                        <h3 class="font-medium text-light-tx dark:text-dark-tx truncate">
                            {curr.title}
                        </h3>
                        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                            {curr.metadata?.schulart || '–'} · 
                            {formatJahrgangsstufe(curr.metadata?.jahrgangsstufe)}
                            {#if curr.metadata?.bp_version}
                                · BP {curr.metadata?.bp_version}
                            {/if}
                        </p>
                    </div>
                    
                    <!-- Badge wenn bearbeitbar -->
                    {#if canEditSubject && curr.write_scope_group_id && 
                        $myTeachingGroups.some(g => g.id === curr.write_scope_group_id)}
                        <span 
                            class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium 
                                   bg-light-bl/20 dark:bg-dark-bl/20 text-light-bl dark:text-dark-bl"
                        >
                            Bearbeitbar
                        </span>
                    {/if}
                </a>
            {/each}
        </div>
        
        <!-- Neues Curriculum Button -->
        {#if showNewButton && canEditSubject}
            <button
                onclick={() => goto(`/knowledge/curriculum/new?subject=${subjectSlug}`)}
                class="w-full sm:w-auto px-4 py-2 text-sm rounded-md bg-primary dark:bg-primary-dark
                   text-white font-medium hover:opacity-90 transition-opacity mt-4"
            >
                + Neues Curriculum anlegen
            </button>
        {/if}
    {/if}
</div>
