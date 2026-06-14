<script>
    import { page } from '$app/stores'
    import { goto } from '$app/navigation'
    import { getCurriculum, deleteContextNode, exportCurriculum } from '$lib/api.js'
    import { curriculumStd } from '$lib/curriculum.js'
    import { user } from '$lib/stores/user.js'
    import CurriculumTable from '$lib/components/CurriculumTable.svelte'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import { ArrowLeft } from 'lucide-svelte'

    let curriculum = $state(null)
    const totalStd = $derived(curriculumStd(curriculum))
    let loading = $state(true)
    let error = $state(null)

    // Löschen
    let confirmDelete = $state(false)
    let deleting = $state(false)
    let deleteError = $state(null)

    // Export
    let exportError = $state(null)
    let exporting = $state(false)

    // Sticky-Footer: nur sichtbar, wenn die oberen Aktionen aus dem Scrollbereich sind
    let scrollEl = $state(null)
    let topActionsEl = $state(null)
    let showStickyFooter = $state(false)

    $effect(() => {
        if (!scrollEl || !topActionsEl) return
        const obs = new IntersectionObserver(
            ([entry]) => { showStickyFooter = !entry.isIntersecting },
            { root: scrollEl, threshold: 0 },
        )
        obs.observe(topActionsEl)
        return () => obs.disconnect()
    })

    function _exportFilename(format) {
        const meta = curriculum?.metadata ?? {}
        const fach = (meta.fach_code ?? 'curriculum').replace(/\s/g, '_')
        const jg = meta.jahrgangsstufe ?? ''
        const date = new Date().toISOString().slice(0, 10)
        return `curriculum_${fach}_${jg}_${date}.${format}`
    }

    async function handleExport(format) {
        if (exporting || !curriculum) return
        exporting = true
        exportError = null
        try {
            await exportCurriculum(curriculum.id, _exportFilename(format), format)
        } catch (e) {
            exportError = e.message || 'Export fehlgeschlagen.'
        } finally {
            exporting = false
        }
    }

    $effect(() => {
        const id = $page.params.id
        let cancelled = false

        loading = true
        ;(async () => {
            try {
                const data = await getCurriculum(id)
                if (cancelled) return
                curriculum = data
            } catch (e) {
                if (!cancelled) error = e.message
            } finally {
                if (!cancelled) loading = false
            }
        })()

        return () => { cancelled = true }
    })

    async function handleDelete() {
        if (deleting || !curriculum) return
        deleting = true
        deleteError = null
        try {
            await deleteContextNode(curriculum.id)
            goto('/knowledge/curricula', { replaceState: true })
        } catch (e) {
            deleteError = e.status === 403
                ? 'Keine Berechtigung — Sie müssen Mitglied der Fachschaft sein.'
                : (e.message || 'Curriculum konnte nicht gelöscht werden.')
            deleting = false
        }
    }
</script>

<div class="h-full flex flex-col relative">
    <!-- Scrollbarer Inhaltsbereich -->
    <div bind:this={scrollEl} class="flex-1 overflow-y-auto p-6 max-w-4xl">
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
                        {#if totalStd > 0}
                            · Gesamt: {totalStd} Std.
                        {/if}
                    </p>
                </div>
                <div bind:this={topActionsEl} class="flex gap-2">
                    {#if curriculum.can_edit}
                        <a
                            href="/knowledge/curriculum/{curriculum.id}/edit"
                            class="px-4 py-2 text-sm rounded-md bg-primary dark:bg-primary-dark
                               text-white font-medium hover:opacity-90 transition-opacity"
                        >
                            Bearbeiten
                        </a>
                        <button
                            onclick={() => { deleteError = null; confirmDelete = true }}
                            class="px-4 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                               text-light-re dark:text-dark-re font-medium
                               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                        >
                            Löschen
                        </button>
                    {/if}
                    <button
                        onclick={() => handleExport('yaml')}
                        disabled={exporting}
                        class="px-4 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                               text-light-tx dark:text-dark-tx font-medium
                               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                               disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        YAML
                    </button>
                    <button
                        onclick={() => handleExport('pdf')}
                        disabled={exporting}
                        class="px-4 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                               text-light-tx dark:text-dark-tx font-medium
                               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                               disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        PDF
                    </button>
                </div>
            </div>

            {#if exportError}
                <div class="mb-4 p-3 rounded-md bg-light-re/10 dark:bg-dark-re/10
                             text-light-re dark:text-dark-re text-sm">
                    {exportError}
                </div>
            {/if}

            <!-- Curriculum-Tabelle -->
            <div class="bg-white dark:bg-dark-bg rounded-lg border border-light-ui-3 dark:border-dark-ui-3">
                <CurriculumTable {curriculum} editMode={false} />
            </div>
        {:else}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                Curriculum nicht gefunden.
            </p>
        {/if}
    </div>

    <!-- Sticky-Footer: überlagert den Inhalt, nur sichtbar wenn obere Aktionen weggescrollt -->
    {#if curriculum && showStickyFooter}
        <div class="absolute bottom-0 left-0 right-0 border-t border-light-ui-3 dark:border-dark-ui-3 bg-light-bg/95 dark:bg-dark-bg/95 backdrop-blur px-6 py-2 flex gap-2 justify-end">
            {#if curriculum.can_edit}
                <a
                    href="/knowledge/curriculum/{curriculum.id}/edit"
                    class="px-4 py-1.5 text-sm rounded-md bg-primary dark:bg-primary-dark
                           text-white font-medium hover:opacity-90 transition-opacity"
                >
                    Bearbeiten
                </a>
            {/if}
            <button
                onclick={() => handleExport('yaml')}
                disabled={exporting}
                class="px-4 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       text-light-tx dark:text-dark-tx font-medium
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                       disabled:opacity-50 disabled:cursor-not-allowed"
            >
                YAML
            </button>
            <button
                onclick={() => handleExport('pdf')}
                disabled={exporting}
                class="px-4 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       text-light-tx dark:text-dark-tx font-medium
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                       disabled:opacity-50 disabled:cursor-not-allowed"
            >
                PDF
            </button>
        </div>
    {/if}
</div>

{#if confirmDelete && curriculum}
    <div class="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-4">
        <div class="bg-white dark:bg-dark-bg-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-6 max-w-md w-full">
            <h3 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-3">
                Curriculum löschen
            </h3>
            <p class="text-light-tx-2 dark:text-dark-tx-2 mb-4">
                Möchten Sie „{curriculum.title}" wirklich löschen? Alle enthaltenen
                Kapitel und Lernsequenzen werden mitgelöscht. Dieser Vorgang kann
                nicht rückgängig gemacht werden.
            </p>
            {#if deleteError}
                <div class="mb-4">
                    <ErrorBanner message={deleteError} />
                </div>
            {/if}
            <div class="flex gap-3 justify-end">
                <button
                    onclick={() => confirmDelete = false}
                    disabled={deleting}
                    class="px-4 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                           text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                           disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    Abbrechen
                </button>
                <button
                    onclick={handleDelete}
                    disabled={deleting}
                    class="px-4 py-2 text-sm rounded-md bg-light-re dark:bg-dark-re text-white
                           hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    {deleting ? 'Wird gelöscht…' : 'Löschen'}
                </button>
            </div>
        </div>
    </div>
{/if}
