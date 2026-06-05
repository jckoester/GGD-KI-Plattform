<script>
    import { goto } from '$app/navigation'
    import { page } from '$app/stores'
    import { user, hasAnyRole } from '$lib/stores/user.js'
    import { subjects, subjectMap } from '$lib/stores/subjects.js'
    import { myTeachingGroups } from '$lib/stores/myGroups.js'
    import { getCurriculaBySubject } from '$lib/api.js'
    import CurriculumList from '$lib/components/CurriculumList.svelte'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import { ArrowLeft } from 'lucide-svelte'

    // Auth-Prüfung: nur teacher/admin
    $effect(() => {
        if ($page.url.pathname.startsWith('/knowledge/curricula') && $user && !hasAnyRole(['teacher', 'admin'])($user)) {
            goto('/chat')
        }
    })

    let loading = $state(true)
    let error = $state(null)
    let curriculaBySubject = $state({})

    // Eigene Fach-IDs extrahieren
    const mySubjectIds = $derived($myTeachingGroups
        .filter(g => g.subject_id)
        .map(g => g.subject_id))

    // Lade Curricula für alle Fächer
    $effect(() => {
        if (!$subjects || $subjects.length === 0) return
        
        loadAllCurricula()
    })

    async function loadAllCurricula() {
        loading = true
        error = null
        try {
            const newCurriculaBySubject = {}
            
            for (const subject of $subjects) {
                try {
                    const curricula = await getCurriculaBySubject(subject.id)
                    newCurriculaBySubject[subject.id] = curricula || []
                } catch (e) {
                    newCurriculaBySubject[subject.id] = []
                }
            }
            
            curriculaBySubject = newCurriculaBySubject
        } catch (e) {
            error = e.message || 'Fehler beim Laden der Curricula'
        } finally {
            loading = false
        }
    }

    // Sortierte Liste der Fächer: eigene Fächer zuerst
    const sortedSubjects = $derived($subjects
        .filter(s => Object.keys(curriculaBySubject).includes(s.id.toString()))
        .sort((a, b) => {
            const aIsMySubject = mySubjectIds.includes(a.id)
            const bIsMySubject = mySubjectIds.includes(b.id)

            if (aIsMySubject && !bIsMySubject) return -1
            if (!aIsMySubject && bIsMySubject) return 1
            return a.name.localeCompare(b.name, 'de')
        }))

    // Gruppe Fächer nach eigenen/anderen
    const groupedSubjects = $derived({
        own: sortedSubjects.filter(s => mySubjectIds.includes(s.id)),
        other: sortedSubjects.filter(s => !mySubjectIds.includes(s.id))
    })

    // Gesamtanzahl der Curricula
    const totalCurricula = $derived(Object.values(curriculaBySubject)
        .reduce((sum, curr) => sum + (curr?.length || 0), 0))
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
                    Curricula
                </h1>
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
                    {totalCurricula} Curricula in {sortedSubjects.length} Fächern
                </p>
            </div>
        </div>

        <!-- Lade-Indikator -->
        {#if loading}
            <LoadingBanner message="Curricula werden geladen…" />
        {:else if error}
            <ErrorBanner message={error} />
        {:else if sortedSubjects.length === 0}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                Keine Curricula verfügbar.
            </p>
        {:else}
            <!-- Eigene Fächer (oben) -->
            {#if groupedSubjects.own.length > 0}
                <div class="mb-8">
                    <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-4">
                        Meine Fächer
                    </h2>
                    <div class="space-y-4">
                        {#each groupedSubjects.own as subject (subject.id)}
                            <div class="bg-light-bg-2 dark:bg-dark-bg-2 rounded-lg border 
                                        border-light-ui-3 dark:border-dark-ui-3 p-4">
                                <h3 class="font-medium text-light-tx dark:text-dark-tx mb-3">
                                    {subject.name}
                                </h3>
                                <CurriculumList
                                    subjectId={subject.id}
                                    subjectSlug={subject.slug}
                                    subjectFachCode={subject.fach_code}
                                    showNewButton={true}
                                />
                            </div>
                        {/each}
                    </div>
                </div>
            {/if}

            <!-- Andere Fächer -->
            {#if groupedSubjects.other.length > 0}
                <div>
                    <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-4">
                        Andere Fächer
                    </h2>
                    <div class="space-y-4">
                        {#each groupedSubjects.other as subject (subject.id)}
                            <div class="bg-light-bg-2 dark:bg-dark-bg-2 rounded-lg border 
                                        border-light-ui-3 dark:border-dark-ui-3 p-4">
                                <h3 class="font-medium text-light-tx dark:text-dark-tx mb-3">
                                    {subject.name}
                                </h3>
                                <CurriculumList 
                                    subjectId={subject.id} 
                                    subjectSlug={subject.slug}
                                    showNewButton={false}
                                />
                            </div>
                        {/each}
                    </div>
                </div>
            {/if}
        {/if}
    </main>
</div>
