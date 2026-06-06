<script>
    import { page } from '$app/stores'
    import { goto } from '$app/navigation'
    import { getFachplaene, createCurriculum } from '$lib/api.js'
    import { user, userHasAnyRole } from '$lib/stores/user.js'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import InfoBanner from '$lib/components/InfoBanner.svelte'

    // Auth-Guard
    $effect(() => {
        if ($user && !userHasAnyRole($user, ['teacher', 'admin'])) {
            goto('/chat')
        }
    })

    // Query-Params für Vorbelegung (Einstieg aus Fach-Ansicht)
    const preFilterCode = $page.url.searchParams.get('fach_code')?.toUpperCase() ?? null

    // ── Fachpläne laden ───────────────────────────────────────────────────────
    let fachplaene = $state([])
    let loadError = $state(null)
    let loadingFachplaene = $state(true)

    $effect(() => {
        loadFachplaene()
    })

    async function loadFachplaene() {
        loadingFachplaene = true
        loadError = null
        try {
            const data = await getFachplaene()
            fachplaene = data || []
        } catch (e) {
            loadError = e.message || 'Bildungspläne konnten nicht geladen werden'
        } finally {
            loadingFachplaene = false
        }
    }

    // ── Metadata aus bp_id extrahieren ────────────────────────────────────────
    const SCHULART_MAP = { GYM: 'Gymnasium', RS: 'Realschule', GMS: 'Gemeinschaftsschule', GS: 'Grundschule', BSO: 'Berufsschule' }

    function parseBpMetadata(node) {
        const bpId = node.metadata?.bp_id || ''
        const breadcrumb = node.metadata?.breadcrumb || []

        const bpVersionMatch = bpId.match(/^BP(\d{4})/)
        const bp_version = bpVersionMatch ? bpVersionMatch[1]
            : (breadcrumb[0]?.match(/\d{4}/)?.[0] || '')

        const schulartMatch = bpId.match(/_(GYM|RS|GMS|GS|BSO)_/)
        const schulart = schulartMatch
            ? (SCHULART_MAP[schulartMatch[1]] || schulartMatch[1])
            : (breadcrumb[1] || '')

        // fach_code: bevorzugt aus den Knoten-Metadaten (vom Import gesetzt);
        // Fallback-Heuristik: letztes bp_id-Segment vor optionalem ".V2"-Suffix
        let fach_code = node.metadata?.fach_code || ''
        if (!fach_code) {
            const cleanId = bpId.replace(/\.\w+$/, '')
            const parts = cleanId.split('_').filter(Boolean)
            fach_code = parts[parts.length - 1] || ''
        }

        return { bp_version, schulart, fach_code }
    }

    // ── Gefilterte + angereicherte Fachplan-Liste ─────────────────────────────
    const enrichedFachplaene = $derived(
        fachplaene.map(fp => {
            const meta = parseBpMetadata(fp)
            const label = fp.metadata?.breadcrumb?.slice(1).join(' › ') || fp.title
            return { ...fp, _meta: meta, _label: label }
        })
    )

    // Fachplan-Optionen: wenn ?fach_code= gesetzt, nur passende zeigen
    const fachplanOptions = $derived(
        preFilterCode
            ? enrichedFachplaene.filter(fp => fp._meta.fach_code.toUpperCase() === preFilterCode)
            : enrichedFachplaene
    )

    // ── Formularfelder ────────────────────────────────────────────────────────
    let selectedFachplanId = $state('')
    let jahrgangsstufe = $state('')
    let saving = $state(false)
    let saveError = $state(null)

    // Auto-select wenn nur ein Fachplan passend
    $effect(() => {
        if (fachplanOptions.length === 1 && !selectedFachplanId) {
            selectedFachplanId = fachplanOptions[0].id
        }
    })

    const selectedFachplan = $derived(
        enrichedFachplaene.find(fp => fp.id === selectedFachplanId) ?? null
    )

    const canSubmit = $derived(
        !!selectedFachplanId && !!jahrgangsstufe.trim() && !saving
    )

    // ── Absenden ──────────────────────────────────────────────────────────────
    async function handleSubmit(e) {
        e.preventDefault()
        if (!canSubmit || !selectedFachplan) return

        saving = true
        saveError = null
        try {
            const meta = selectedFachplan._meta
            const payload = {
                // Node-UUID des Fachplan-Knotens (nicht der Geschäftsschlüssel metadata.fachplan_id)
                fachplan_node_id: selectedFachplan.id,
                fach_code: meta.fach_code,
                schulart: meta.schulart,
                bp_version: meta.bp_version,
                jahrgangsstufe: jahrgangsstufe.trim(),
                schule: '',
            }
            const node = await createCurriculum(payload)
            goto(`/knowledge/curriculum/${node.id}/edit`)
        } catch (e) {
            if (e.status === 403) {
                saveError = 'Keine Berechtigung — Sie müssen Mitglied der Fachschaft sein.'
            } else if (e.status === 422) {
                saveError = e.message || 'Für diesen Bildungsplan wurde noch kein Plan importiert.'
            } else {
                saveError = e.message || 'Fehler beim Erstellen des Curriculums.'
            }
        } finally {
            saving = false
        }
    }
</script>

<div class="max-w-2xl mx-auto px-4 py-8">
    <div class="mb-6">
        <a
            href="/knowledge/curricula"
            class="text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx"
        >
            ← Curricula
        </a>
        <h1 class="mt-2 text-2xl font-bold text-light-tx dark:text-dark-tx">
            Neues Curriculum anlegen
        </h1>
        <p class="mt-1 text-sm text-light-tx-2 dark:text-dark-tx-2">
            Wählen Sie den Bildungsplan und die Jahrgangsstufe. Das Curriculum wird als leere Vorlage angelegt.
        </p>
    </div>

    {#if loadingFachplaene}
        <LoadingBanner message="Bildungspläne werden geladen…" />
    {:else if loadError}
        <ErrorBanner message={loadError} />
    {:else if fachplanOptions.length === 0}
        <InfoBanner message={preFilterCode
            ? `Für Fach „${preFilterCode}" ist kein Bildungsplan importiert. Bitte zuerst den Bildungsplan importieren.`
            : 'Noch kein Bildungsplan importiert. Bitte zuerst einen Bildungsplan importieren.'
        } />
    {:else}
        <form onsubmit={handleSubmit} class="space-y-6">

            <!-- Bildungsplan-Auswahl -->
            <div>
                <label
                    for="fachplan"
                    class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                >
                    Bildungsplan <span class="text-light-re dark:text-dark-re">*</span>
                </label>
                {#if fachplanOptions.length === 1}
                    <!-- Nur ein Plan: direkt anzeigen, kein Dropdown -->
                    <div class="px-3 py-2 rounded border border-light-ui-3 dark:border-dark-ui-3
                                bg-light-bg-2 dark:bg-dark-bg-2 text-sm text-light-tx dark:text-dark-tx">
                        {fachplanOptions[0]._label}
                    </div>
                {:else}
                    <select
                        id="fachplan"
                        bind:value={selectedFachplanId}
                        class="w-full px-3 py-2 rounded border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                               text-sm focus:outline-none focus:border-primary dark:focus:border-primary-dark"
                    >
                        <option value="">— Bildungsplan wählen —</option>
                        {#each fachplanOptions as fp (fp.id)}
                            <option value={fp.id}>{fp._label}</option>
                        {/each}
                    </select>
                {/if}

                {#if selectedFachplan}
                    <p class="mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2">
                        {selectedFachplan._meta.schulart} · BP {selectedFachplan._meta.bp_version} · Fach-Code: {selectedFachplan._meta.fach_code}
                    </p>
                {/if}
            </div>

            <!-- Jahrgangsstufe -->
            <div>
                <label
                    for="jahrgangsstufe"
                    class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                >
                    Jahrgangsstufe / Stufenband <span class="text-light-re dark:text-dark-re">*</span>
                </label>
                <input
                    id="jahrgangsstufe"
                    type="text"
                    bind:value={jahrgangsstufe}
                    placeholder="z. B. 7 oder 7/8 oder 5–6"
                    class="w-full px-3 py-2 rounded border border-light-ui-3 dark:border-dark-ui-3
                           bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                           text-sm focus:outline-none focus:border-primary dark:focus:border-primary-dark"
                />
                <p class="mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2">
                    Freie Eingabe — z. B. einzelne Stufe oder Stufenband
                </p>
            </div>

            {#if saveError}
                <ErrorBanner message={saveError} />
            {/if}

            <!-- Aktionen -->
            <div class="flex items-center gap-3 pt-2">
                <button
                    type="submit"
                    disabled={!canSubmit}
                    class="px-4 py-2 rounded text-sm font-medium transition-colors
                           bg-primary dark:bg-primary-dark text-white
                           disabled:opacity-50 disabled:cursor-not-allowed
                           hover:opacity-90"
                >
                    {saving ? 'Wird angelegt…' : 'Curriculum anlegen'}
                </button>
                <a
                    href="/knowledge/curricula"
                    class="px-4 py-2 rounded text-sm text-light-tx-2 dark:text-dark-tx-2
                           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                >
                    Abbrechen
                </a>
            </div>
        </form>
    {/if}
</div>
