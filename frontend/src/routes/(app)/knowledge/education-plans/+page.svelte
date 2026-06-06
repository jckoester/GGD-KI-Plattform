<script>
    import { goto } from '$app/navigation'
    import { page } from '$app/stores'
    import { user, userHasAnyRole } from '$lib/stores/user.js'
    import { subjects } from '$lib/stores/subjects.js'
    import { myGroups, myTeachingGroups } from '$lib/stores/myGroups.js'
    import BildungsplanTree from '$lib/components/BildungsplanTree.svelte'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'
    import { ArrowLeft } from 'lucide-svelte'

    // Auth-Prüfung: nur teacher/admin
    $effect(() => {
        if ($page.url.pathname.startsWith('/knowledge/education-plans') && $user && !userHasAnyRole($user, ['teacher', 'admin'])) {
            goto('/chat')
        }
    })

    let selectedSubjectId = $state(null)

    // Eigene Fach-IDs extrahieren (teaching_groups + subject_department, identisch zur Sidebar)
    const mySubjectIds = $derived([...new Set([
        ...$myTeachingGroups.filter(g => g.subject_id).map(g => g.subject_id),
        ...$myGroups.filter(g => g.type === 'subject_department' && g.subject_id != null).map(g => g.subject_id)
    ])])

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

    function selectSubject(subjectId) {
        selectedSubjectId = subjectId
    }

    // Gruppe Fächer nach eigenen/anderen
    const groupedSubjects = $derived({
        own: sortedSubjects.filter(s => mySubjectIds.includes(s.id)),
        other: sortedSubjects.filter(s => !mySubjectIds.includes(s.id))
    })
</script>

<div class="h-full overflow-y-auto p-6 max-w-6xl">
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
        <div class="mb-6 flex items-center gap-3">
            <label for="subject-select"
                   class="text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 whitespace-nowrap">
                Fach:
            </label>
            <select
                id="subject-select"
                value={selectedSubjectId}
                onchange={(e) => selectSubject(Number(e.currentTarget.value))}
                class="px-3 py-1.5 text-sm rounded-md border
                       border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg
                       text-light-tx dark:text-dark-tx
                       focus:outline-none focus:border-primary dark:focus:border-primary-dark
                       transition-colors"
            >
                {#if groupedSubjects.own.length > 0}
                    <optgroup label="Meine Fächer">
                        {#each groupedSubjects.own as subject (subject.id)}
                            <option value={subject.id}>{subject.name}</option>
                        {/each}
                    </optgroup>
                {/if}
                {#if groupedSubjects.other.length > 0}
                    <optgroup label="Weitere Fächer">
                        {#each groupedSubjects.other as subject (subject.id)}
                            <option value={subject.id}>{subject.name}</option>
                        {/each}
                    </optgroup>
                {/if}
            </select>
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
        {/if}
    {/if}
</div>
