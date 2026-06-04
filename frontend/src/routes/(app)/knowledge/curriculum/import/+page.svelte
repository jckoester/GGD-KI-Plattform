<script>
    import { page } from '$app/stores'
    import { goto } from '$app/navigation'
    import { getFachplaene, convertCurriculum, createCurriculumFromDraft } from '$lib/api.js'
    import { draftToPreview } from '$lib/curriculumImport.js'
    import CurriculumTable from '$lib/components/CurriculumTable.svelte'
    import WarningBanner from '$lib/components/WarningBanner.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'
    import { sidebarSubjectSections } from '$lib/stores/sidebarSections.js'
    import { ArrowLeft, Upload, Check, AlertCircle, FileText, X } from 'lucide-svelte'

    // Schritt-Zustand
    let step = $state('upload') // 'upload' | 'converting' | 'review' | 'saving'
    let error = $state(null)

    // Stufe 1: Upload-Formular
    let file = $state(null)
    let fachplanId = $state($page.url.searchParams.get('subject') ?? '')
    let fach = $state('')
    let jahrgangsstufe = $state('')
    let fachplaene = $state([])
    let loadingFachplaene = $state(true)

    // Fächerliste der Lehrkraft — identische Quelle wie Sidebar (teaching_groups + subject_departments)
    const mySubjects = $derived(
        $sidebarSubjectSections.filter(s => s.type === 'teacher')
    )

    // Stufe 2: Review
    let draft = $state(null)
    let preview = $state(null)

    // Lade Bildungspläne beim Mount
    $effect(() => {
        loadFachplaene()
    })

    async function loadFachplaene() {
        loadingFachplaene = true
        error = null
        try {
            const data = await getFachplaene()
            fachplaene = data.items || data || []
            // Wenn subject-Param vorhanden, versuche fachplanId über subject_slug zu setzen
            if (fachplanId && !fachplaene.some(f => f.id == fachplanId)) {
                const matching = fachplaene.find(f => f.metadata?.subject_slug === fachplanId)
                if (matching) fachplanId = matching.id
            }
        } catch (e) {
            error = e.message
        } finally {
            loadingFachplaene = false
        }
    }

    // Datei-Change-Handler
    function handleFileChange(event) {
        const selectedFile = event.target.files?.[0]
        if (selectedFile) {
            // Validierung
            const validTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
            const maxSize = 20 * 1024 * 1024 // 20 MB

            if (!validTypes.includes(selectedFile.type)) {
                error = 'Bitte wählen Sie eine PDF- oder Word-Datei (.docx) aus.'
                file = null
                event.target.value = ''
                return
            }

            if (selectedFile.size > maxSize) {
                error = 'Die Datei ist zu groß. Maximale Größe: 20 MB.'
                file = null
                event.target.value = ''
                return
            }

            file = selectedFile
            error = null
        }
    }

    // Extraktion starten
    async function handleConvert() {
        if (!file) { error = 'Bitte wählen Sie eine Datei aus.'; return }
        if (!fachplanId) { error = 'Bitte wählen Sie einen Bildungsplan aus.'; return }
        if (!fach.trim()) { error = 'Bitte geben Sie das Fach ein.'; return }
        if (!jahrgangsstufe.trim()) { error = 'Bitte geben Sie die Jahrgangsstufe ein.'; return }

        step = 'converting'
        error = null

        try {
            const fd = new FormData()
            fd.append('file', file)
            fd.append('fachplan_id', fachplanId)
            fd.append('fach', fach.trim())
            fd.append('jahrgangsstufe', jahrgangsstufe.trim())

            const response = await convertCurriculum(fd)

            // Prüfe auf unsupported_format
            if (response.unsupported_format) {
                step = 'unsupported'
                return
            }

            draft = response
            preview = draftToPreview(draft)
            step = 'review'
        } catch (e) {
            error = e.message
            step = 'upload'
        }
    }

    // Speichern
    async function handleSave() {
        step = 'saving'
        error = null

        try {
            const curriculum = await createCurriculumFromDraft(draft.data)
            goto(`/knowledge/curriculum/${curriculum.id}`, { replaceState: true })
        } catch (e) {
            error = e.message
            step = 'review'
        }
    }

    // Zurück zu Upload
    function goBackToUpload() {
        step = 'upload'
        error = null
    }

    // Zurück zu Review
    function goBackToReview() {
        step = 'review'
        error = null
    }

    // Abbrechen
    function cancel() {
        goto('/knowledge', { replaceState: true })
    }

    // Warnungen für Review extrahieren
    const globalWarnings = $derived.by(() => {
        if (!draft) return []
        return draft.warnings || []
    })

    const fieldWarnings = $derived.by(() => {
        if (!draft || !draft.data) return []
        const warnings = []
        // Suche nach _warning Markern im Draft
        const chapters = draft.data.kapitel || []
        chapters.forEach((kap, ki) => {
            const lernsequenzen = kap.lernsequenzen || []
            lernsequenzen.forEach((ls, li) => {
                const eintraege = ls.eintraege || []
                eintraege.forEach((e, ei) => {
                    if (e._warning) {
                        warnings.push({
                            index: warnings.length + 1,
                            message: e._warning,
                            location: `Kapitel ${ki + 1}, Lernsequenz ${li + 1}`
                        })
                    }
                    // Prüfe IK- und PK-Resolved auf Warnungen
                    if (e.ik_resolved) {
                        e.ik_resolved.forEach(ik => {
                            if (ik._warning) {
                                warnings.push({
                                    index: warnings.length + 1,
                                    message: ik._warning,
                                    location: `Kapitel ${ki + 1}, Lernsequenz ${li + 1}, IK: ${ik.nr || 'unbekannt'}`
                                })
                            }
                        })
                    }
                    if (e.pk_resolved) {
                        e.pk_resolved.forEach(pk => {
                            if (pk._warning) {
                                warnings.push({
                                    index: warnings.length + 1,
                                    message: pk._warning,
                                    location: `Kapitel ${ki + 1}, Lernsequenz ${li + 1}, PK: ${pk.id || 'unbekannt'}`
                                })
                            }
                        })
                    }
                })
            })
        })
        return warnings
    })

    const hasWarnings = $derived.by(() => globalWarnings.length > 0 || fieldWarnings.length > 0)

    const formatInfo = $derived.by(() => {
        if (!draft) return null
        return draft.format || 'Unbekanntes Format'
    })
</script>

<div class="h-full overflow-y-auto">
    <main class="p-6 max-w-6xl">
        <!-- Header mit Zurück-Button -->
        <div class="mb-6">
            <a
                href="/knowledge"
                class="flex items-center gap-1 mb-2 text-sm text-light-tx-2 dark:text-dark-tx-2
                     hover:text-light-tx dark:hover:text-dark-tx transition-colors"
                onclick={(e) => { e.preventDefault(); cancel() }}
            >
                <ArrowLeft class="w-4 h-4" /> Zurück zur Wissensdatenbank
            </a>
            
            <div class="flex items-center gap-2">
                <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">
                    Curriculum importieren
                </h1>
            </div>
        </div>

        <!-- Fehleranzeige (global) -->
        {#if error && step !== 'unsupported'}
            <ErrorBanner message={error} />
        {/if}

        <!-- ========================================
             STUFE 1: UPLOAD-FORMULAR
             ======================================== -->
        {#if step === 'upload'}
            <div class="max-w-2xl">
                <p class="text-light-tx-2 dark:text-dark-tx-2 mb-6">
                    Laden Sie ein PDF- oder Word-Dokument eines Curriculums hoch. 
                    Der Assistent extrahiert automatisch die Struktur und Inhalte.
                </p>

                <!-- Dateiauswahl -->
                <div class="mb-6">
                    <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-2">
                        Curriculum-Datei *
                    </label>
                    <div class="relative">
                        <input
                            type="file"
                            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                            onchange={handleFileChange}
                            class="block w-full text-sm text-light-tx dark:text-dark-tx
                                   file:mr-4 file:py-2 file:px-4 file:rounded-md
                                   file:border-0 file:text-sm file:font-semibold
                                   file:bg-primary dark:file:bg-primary-dark file:text-white
                                   file:hover:opacity-90 file:cursor-pointer
                                   border border-light-ui-3 dark:border-dark-ui-3 rounded-md
                                   bg-light-bg dark:bg-dark-bg
                                   hover:border-primary dark:hover:border-primary-dark
                                   transition-colors"
                        />
                    </div>
                    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mt-1">
                        Unterstützt: PDF, Word (.docx) | Max. 20 MB
                    </p>
                </div>

                <!-- Bildungsplan-Auswahl -->
                <div class="mb-6">
                    <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-2">
                        Bildungsplan *
                    </label>
                    {#if loadingFachplaene}
                        <div class="p-3 border border-light-ui-3 dark:border-dark-ui-3 rounded-md">
                            <LoadingBanner message="Bildungspläne werden geladen…" />
                        </div>
                    {:else if fachplaene.length === 0}
                        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                            Keine Bildungspläne verfügbar.
                        </p>
                    {:else}
                        <select
                            bind:value={fachplanId}
                            class="w-full p-3 border border-light-ui-3 dark:border-dark-ui-3 rounded-md
                                   bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                                   hover:border-primary dark:hover:border-primary-dark
                                   transition-colors"
                        >
                            <option value="">Bitte Bildungsplan auswählen</option>
                            {#each fachplaene as fp}
                                <option value={fp.id}>
                                    {fp.title} ({fp.metadata?.schulart || '–'}) – BP {fp.metadata?.bp_version || '–'}
                                </option>
                            {/each}
                        </select>
                    {/if}
                </div>

                <!-- Fach -->
                <div class="mb-6">
                    <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-2">
                        Fach *
                    </label>
                    {#if mySubjects.length === 0}
                        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                            Keine Fächer gefunden. Bitte zuerst einer Fachschaft beitreten.
                        </p>
                    {:else}
                        <select
                            bind:value={fach}
                            class="w-full p-3 border border-light-ui-3 dark:border-dark-ui-3 rounded-md
                                   bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                                   hover:border-primary dark:hover:border-primary-dark
                                   transition-colors"
                        >
                            <option value="">Bitte Fach auswählen</option>
                            {#each mySubjects as sub}
                                <option value={sub.name}>{sub.name}</option>
                            {/each}
                        </select>
                    {/if}
                </div>

                <!-- Jahrgangsstufe -->
                <div class="mb-6">
                    <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-2">
                        Jahrgangsstufe *
                    </label>
                    <input
                        type="text"
                        bind:value={jahrgangsstufe}
                        placeholder="z. B. 7"
                        class="w-full p-3 border border-light-ui-3 dark:border-dark-ui-3 rounded-md
                               bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                               placeholder:text-light-tx-2 dark:placeholder:text-dark-tx-2
                               hover:border-primary dark:hover:border-primary-dark
                               transition-colors"
                    />
                </div>

                <!-- Aktionen -->
                <div class="flex gap-4">
                    <button
                        onclick={cancel}
                        class="px-6 py-3 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                               text-light-tx dark:text-dark-tx font-medium
                               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                    >
                        Abbrechen
                    </button>
                    <button
                        onclick={handleConvert}
                        disabled={!file || !fachplanId || !fach.trim() || !jahrgangsstufe.trim()}
                        class="px-6 py-3 text-sm rounded-md bg-primary dark:bg-primary-dark
                               text-white font-medium hover:opacity-90 transition-opacity
                               disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                        <Upload class="w-4 h-4" />
                        Dokument analysieren
                    </button>
                </div>
            </div>

        <!-- ========================================
             STUFE 2: CONVERTING (Ladezustand)
             ======================================== -->
        {:else if step === 'converting'}
            <div class="max-w-2xl">
                <LoadingBanner message="Dokument wird analysiert… Dies kann 10–30 Sekunden dauern." />
                <div class="mt-6 p-6 border border-light-ui-3 dark:border-dark-ui-3 rounded-lg
                           bg-light-bg-2 dark:bg-dark-bg-2">
                    <div class="flex items-center gap-3">
                        <FileText class="w-6 h-6 text-light-tx-2 dark:text-dark-tx-2" />
                        <div>
                            <p class="font-medium text-light-tx dark:text-dark-tx">{file?.name || 'Datei'}</p>
                            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                                {Math.round((file?.size || 0) / 1024)} KB
                            </p>
                        </div>
                    </div>
                </div>
            </div>

        <!-- ========================================
             STUFE 3: REVIEW
             ======================================== -->
        {:else if step === 'review'}
            <div class="space-y-6">
                <!-- Format-Info -->
                {#if formatInfo}
                    <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm
                               bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx-2 dark:text-dark-tx-2">
                        <FileText class="w-4 h-4" />
                        {formatInfo}
                    </div>
                {/if}

                <!-- Globale Warnungen -->
                {#if globalWarnings.length > 0}
                    <div class="space-y-2">
                        {#each globalWarnings as warning}
                            <WarningBanner message={warning} />
                        {/each}
                    </div>
                {/if}

                <!-- Feld-Warnungen -->
                {#if fieldWarnings.length > 0}
                    <div class="p-4 border border-light-ui-3 dark:border-dark-ui-3 rounded-lg
                               bg-light-ui-1 dark:bg-dark-ui-1">
                        <h3 class="font-semibold text-light-tx dark:text-dark-tx mb-3 flex items-center gap-2">
                            <AlertCircle class="w-5 h-5" />
                            Zu prüfende Felder ({fieldWarnings.length})
                        </h3>
                        <ul class="space-y-2 text-sm">
                            {#each fieldWarnings as warning}
                                <li class="text-light-tx-2 dark:text-dark-tx-2">
                                    <span class="font-medium text-light-tx dark:text-dark-tx">{warning.index}.</span> 
                                    {warning.location}: {warning.message}
                                </li>
                            {/each}
                        </ul>
                    </div>
                {/if}

                <!-- Hinweis zur späteren Bearbeitung -->
                {#if hasWarnings}
                    <div class="p-4 border border-light-ui-3 dark:border-dark-ui-3 rounded-lg
                               bg-light-ui-1 dark:bg-dark-ui-1">
                        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                            <strong class="text-light-tx dark:text-dark-tx">Hinweis:</strong> 
                            Sie können die extrahierten Daten nach dem Speichern über den Inline-Editor korrigieren.
                        </p>
                    </div>
                {/if}

                <!-- Vorschau-Tabelle -->
                {#if preview}
                    <div class="border border-light-ui-3 dark:border-dark-ui-3 rounded-lg overflow-x-auto">
                        <CurriculumTable curriculum={preview} editMode={false} />
                    </div>
                {/if}

                <!-- Aktionen -->
                <div class="flex gap-4">
                    <button
                        onclick={goBackToUpload}
                        class="px-6 py-3 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                               text-light-tx dark:text-dark-tx font-medium
                               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors flex items-center gap-2"
                    >
                        <ArrowLeft class="w-4 h-4" />
                        Zurück
                    </button>
                    <button
                        onclick={handleSave}
                        disabled={step === 'saving'}
                        class="px-6 py-3 text-sm rounded-md bg-primary dark:bg-primary-dark
                               text-white font-medium hover:opacity-90 transition-opacity
                               disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                        {#if step === 'saving'}
                            <LoadingBanner message="Speichern…" />
                        {:else}
                            <Check class="w-4 h-4" />
                            Curriculum speichern
                        {/if}
                    </button>
                </div>
            </div>

        <!-- ========================================
             STUFE 4: UNSUPPORTED FORMAT
             ======================================== -->
        {:else if step === 'unsupported'}
            <div class="max-w-2xl">
                <div class="p-6 border border-light-ui-3 dark:border-dark-ui-3 rounded-lg
                           bg-light-ui-1 dark:bg-dark-ui-1">
                    <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-3">
                        Dieses Format wird nicht als strukturiertes Curriculum unterstützt
                    </h2>
                    <p class="text-light-tx-2 dark:text-dark-tx-2 mb-4">
                        Das hochgeladene Dokument kann nicht automatisch als strukturiertes Curriculum 
                        importiert werden. Sie können es stattdessen als allgemeines Dokument hochladen.
                    </p>
                    <div class="flex gap-4">
                        <button
                            onclick={() => goto(`/knowledge/new?content_type=document`)}
                            class="px-6 py-3 text-sm rounded-md bg-primary dark:bg-primary-dark
                                   text-white font-medium hover:opacity-90 transition-opacity"
                        >
                            Als Dokument hochladen
                        </button>
                        <button
                            onclick={goBackToUpload}
                            class="px-6 py-3 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                                   text-light-tx dark:text-dark-tx font-medium
                                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                        >
                            Andere Datei auswählen
                        </button>
                    </div>
                </div>
            </div>
        {/if}
    </main>
</div>
