<script>
    import ZurueckLink from '$lib/components/ZurueckLink.svelte'
    import { goto } from '$app/navigation'
    import { page } from '$app/stores'
    import { user, userHasAnyRole } from '$lib/stores/user.js'
    import { subjects } from '$lib/stores/subjects.js'
    import { myGroups, myTeachingGroups } from '$lib/stores/myGroups.js'
    import { getCurriculaBySubject } from '$lib/api.js'
    import CurriculumList from '$lib/components/CurriculumList.svelte'
    import FaecherFilter from '$lib/components/FaecherFilter.svelte'
    import { faecherFiltern } from '$lib/curriculum_baender.js'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import PageBody from '$lib/components/PageBody.svelte'
    import StufenHinweis from '$lib/components/StufenHinweis.svelte'

    // Auth-Prüfung: nur teacher/admin
    $effect(() => {
        if ($page.url.pathname.startsWith('/knowledge/curricula') && $user && !userHasAnyRole($user, ['teacher', 'admin'])) {
            goto('/chat')
        }
    })

    let loading = $state(true)
    let error = $state(null)
    let curriculaBySubject = $state({})

    // Eigene Fach-IDs extrahieren (teaching_groups + subject_department, identisch zur Sidebar)
    const mySubjectIds = $derived([...new Set([
        ...$myTeachingGroups.filter(g => g.subject_id).map(g => g.subject_id),
        ...$myGroups.filter(g => g.type === 'subject_department' && g.subject_id != null).map(g => g.subject_id)
    ])])

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

    // Filter (0.46): alle, nur eigene oder ein bestimmtes Fach. Ohne eigene Fächer: alle.
    let filter = $state(null)
    let fachWahl = $state('')
    const filterWert = $derived(filter ?? (mySubjectIds.length ? 'eigene' : 'alle'))
    const anzahlJeFach = $derived(Object.fromEntries(
        Object.entries(curriculaBySubject).map(([id, c]) => [id, c?.length ?? 0])))
    const sichtbareFaecher = $derived(faecherFiltern($subjects, {
        eigene: mySubjectIds, filter: filterWert, fachId: fachWahl ? Number(fachWahl) : null, anzahl: anzahlJeFach,
    }))

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

    // Gesamtanzahl der Curricula
    const totalCurricula = $derived(Object.values(curriculaBySubject)
        .reduce((sum, curr) => sum + (curr?.length || 0), 0))
</script>

<PageBody breit>
  <StufenHinweis eintrag="curricula" />
        <!-- Kopfzeile -->
        <div class="flex items-center justify-between mb-6">
            <div>
                <ZurueckLink href="/knowledge" label="Bibliothek" />
                <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">
                    Curricula
                </h1>
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
                    {totalCurricula} Curricula in {Object.values(anzahlJeFach).filter((n) => n > 0).length} Fächern
                    · <a href="/knowledge/year-plans" class="text-light-bl dark:text-dark-bl hover:underline">Jahresverlaufspläne</a>
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
            <!-- Filter (0.46; seit 0.59 gemeinsam mit den Jahresverlaufsplänen) -->
            <FaecherFilter faecher={$subjects} eigene={mySubjectIds} wert={filterWert} bind:fachWahl
                onwahl={(w) => (filter = w)} />

            {#if sichtbareFaecher.length === 0}
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                    {filterWert === 'eigene' ? 'Du bist in keinem Fach Mitglied der Fachschaft oder einer Unterrichtsgruppe.' : 'Keine Curricula verfügbar.'}
                </p>
            {/if}
            <div class="space-y-3">
                {#each sichtbareFaecher as subject (subject.id)}
                    <!-- Je Fach einklappbar; eigene und ein gezielt gewähltes Fach zu Beginn offen. -->
                    <details
                        class="bg-light-bg-2 dark:bg-dark-bg-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-4"
                        open={!!fachWahl || mySubjectIds.includes(subject.id)}
                    >
                        <summary class="cursor-pointer flex items-baseline gap-2">
                            <span class="text-lg font-semibold text-light-tx dark:text-dark-tx">{subject.name}</span>
                            <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">({anzahlJeFach[subject.id] ?? 0})</span>
                        </summary>
                        <a href="/knowledge/year-plans?fach={subject.id}" class="mt-2 inline-block text-xs text-light-bl dark:text-dark-bl hover:underline">
                            Jahresverlaufspläne {subject.name}
                        </a>
                        <div class="mt-3">
                            <CurriculumList
                                subjectId={subject.id}
                                subjectFachCode={subject.fach_code}
                                showNewButton={mySubjectIds.includes(subject.id)}
                            />
                        </div>
                    </details>
                {/each}
            </div>
        {/if}
</PageBody>
