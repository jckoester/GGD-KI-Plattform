<script>
    import { goto } from '$app/navigation'
    import { page } from '$app/stores'
    import { user, hasAnyRole } from '$lib/stores/user.js'
    import { subjects } from '$lib/stores/subjects.js'
    import { myTeachingGroups } from '$lib/stores/myGroups.js'
    import BildungsplanTree from '$lib/components/BildungsplanTree.svelte'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import { ArrowLeft } from 'lucide-svelte'

    // Auth-Prüfung: nur teacher/admin
    $effect(() => {
        if ($page.url.pathname.startsWith('/knowledge/education-plans') && $user && !hasAnyRole(['teacher', 'admin'])($user)) {
            goto('/chat')
        }
    })

    let selectedSubjectId = $state(null)
    let loading = $state(false)
    let error = $state(null)

    // Eigene Fach-IDs extrahieren
    const mySubjectIds = $derived($myTeachingGroups
        .filter(g => g.subject_id)
        .map(g => g.subject_id))

    // Sortierte Fächer: eigene Fächer zuerst
    const sortedSubjects = $derived([...$subjects]
        .sort((a, b) => {
            const aIsMySubject = mySubjectIds.includes(a.id)
            const bIsMySubject = mySubjectIds.includes(b.id)

            if (aIsMySubject && !bIsMySubject) return -1
            if (!aIsMySubject && bIsMySubject) return 1
            return a.name.localeCompare(b.name, 'de')
        }))

    // Setze erstes eigenes Fach als Standard, sonst erstes Fach
    $effect(() => {
        if (sortedSubjects.length > 0 && selectedSubjectId === null) {
            const firstOwn = sortedSubjects.find(s => mySubjectIds.includes(s.id))
            selectedSubjectId = firstOwn?.id || sortedSubjects[0]?.id
        }
    })

    // Wechsle Fach
    function selectSubject(subjectId) {
        selectedSubjectId = subjectId
        // Reset von Fehlerstatus
        error = null
    }

    // Gruppe Fächer nach eigenen/anderen
    const groupedSubjects = $derived({
        own: sortedSubjects.filter(s => mySubjectIds.includes(s.id)),
        other: sortedSubjects.filter(s => !mySubjectIds.includes(s.id))
    })
</script>

<div class="flex min-h-0 flex-1">
    <main class="flex-1 overflow-y-auto p-6 max-w-6xl">
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
                    Bildungspläne
                </h1>
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
                    Wählen Sie ein Fach aus, um den Bildungsplan anzuzeigen
                </p>
            </div>
        </div>

        <!-- Lade-Indikator für Fächer -->
        {#if $subjects.length === 0}
            <LoadingBanner message="Fächer werden geladen…" />
        {:else if sortedSubjects.length === 0}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                Keine Fächer verfügbar.
            </p>
        {:else}
            <!-- Fachwahl -->
            <div class="mb-6">
                <h2 class="text-sm font-semibold uppercase tracking-wide 
                       text-light-tx-2 dark:text-dark-tx-2 mb-3">
                    Fach auswählen
                </h2>
                
                <div class="flex flex-wrap gap-2">
                    <!-- Eigene Fächer (fett markiert) -->
                    {#each groupedSubjects.own as subject (subject.id)}
                        <button
                            onclick={() => selectSubject(subject.id)}
                            class="px-3 py-1.5 text-sm rounded-md border transition-colors
                                   {selectedSubjectId === subject.id
                                       ? 'border-primary dark:border-primary-dark bg-primary/10 dark:bg-primary-dark/10 text-primary dark:text-primary-dark font-medium'
                                       : 'border-light-ui-3 dark:border-dark-ui-3 text-light-tx dark:text-dark-tx hover:border-primary dark:hover:border-primary-dark font-medium'}"
                        >
                            {subject.name}
                        </button>
                    {/each}
                    
                    <!-- Andere Fächer -->
                    {#each groupedSubjects.other as subject (subject.id)}
                        <button
                            onclick={() => selectSubject(subject.id)}
                            class="px-3 py-1.5 text-sm rounded-md border transition-colors
                                   {selectedSubjectId === subject.id
                                       ? 'border-primary dark:border-primary-dark bg-primary/10 dark:bg-primary-dark/10 text-primary dark:text-primary-dark'
                                       : 'border-light-ui-3 dark:border-dark-ui-3 text-light-tx dark:text-dark-tx hover:border-primary dark:hover:border-primary-dark'}"
                        >
                            {subject.name}
                        </button>
                    {/each}
                </div>
            </div>

            <!-- Bildungsplan-Tree für ausgewähltes Fach -->
            {#if selectedSubjectId}
                <div class="bg-light-bg-2 dark:bg-dark-bg-2 rounded-lg border 
                            border-light-ui-3 dark:border-dark-ui-3 p-6">
                    <BildungsplanTree 
                        subjectId={selectedSubjectId}
                        subjectSlug={sortedSubjects.find(s => s.id === selectedSubjectId)?.slug}
                    />
                </div>
            {:else}
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                    Bitte wählen Sie ein Fach aus.
                </p>
            {/if}
        {/if}
    </main>
</div>
