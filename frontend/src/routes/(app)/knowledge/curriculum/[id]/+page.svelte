<script>
    import { page } from '$app/stores'
    import { goto } from '$app/navigation'
    import { getCurriculum } from '$lib/api.js'
    import { user } from '$lib/stores/user.js'
    import CurriculumTable from '$lib/components/CurriculumTable.svelte'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import { ArrowLeft } from 'lucide-svelte'

    let curriculum = $state(null)
    let loading = $state(true)
    let error = $state(null)

    $effect(async () => {
        try {
            curriculum = await getCurriculum($page.params.id)
        } catch (e) {
            error = e.message
        } finally {
            loading = false
        }
    })
</script>

<div class="flex min-h-0 flex-1">
    <main class="flex-1 overflow-y-auto p-6 max-w-4xl">
        {#if loading}
            <LoadingBanner />
        {:else if error}
            <ErrorBanner message={error} />
        {:else if curriculum}
            <!-- Kopfzeile mit Metadaten und Aktionen -->
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
                        {curriculum.title}
                    </h1>
                    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
                        {curriculum.metadata?.schule} · 
                        {curriculum.metadata?.schulart} · 
                        BP {curriculum.metadata?.bp_version} · 
                        Klasse {curriculum.metadata?.jahrgangsstufe}
                    </p>
                </div>
                <div class="flex gap-2">
                    {#if curriculum.can_edit}
                        <a 
                            href="/knowledge/curriculum/{curriculum.id}/edit"
                            class="px-4 py-2 text-sm rounded-md bg-primary dark:bg-primary-dark
                               text-white font-medium hover:opacity-90 transition-opacity"
                        >
                            Bearbeiten
                        </a>
                    {/if}
                    <!-- Export-Buttons kommen in Schritt 5 -->
                </div>
            </div>

            <!-- Curriculum-Tabelle -->
            <div class="bg-white dark:bg-dark-bg rounded-lg border border-light-ui-3 dark:border-dark-ui-3">
                <CurriculumTable {curriculum} editMode={false} />
            </div>
        {:else}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                Curriculum nicht gefunden.
            </p>
        {/if}
    </main>
</div>
