<script>
    /**
     * Curricula eines Fachs nach Fassung und Band des Bildungsplans (0.46, Schritt 8).
     *
     * Fassungen: erst geltende, dann kommende, ältere eingeklappt. Darin die Bänder aus dem Plan
     * und je Band die Curricula. Lehrkräfte sehen am Band den Link zur IK-Abdeckung über alle
     * Curricula des Bands. Wer Curricula anlegen darf, sieht auch Bänder ohne Curriculum.
     *
     * Props:
     * - subjectId: ID des Fachs
     * - subjectFachCode: Bildungsplan-Fachkürzel (z. B. 'M', 'CH') — für die Vorbelegung der
     *   Curriculum-Neuanlage. NICHT der Slug! Fehlt der Code, wird ohne Vorbelegung verlinkt.
     * - showNewButton: boolean (Default: true) — „Neues Curriculum“ und „Aus YAML importieren“
     *   (0.56) für Fachschaft und Admins
     */
    import { getCurriculaNachBaendern } from '$lib/api.js'
    import { user } from '$lib/stores/user.js'
    import { myGroups, myTeachingGroups } from '$lib/stores/myGroups.js'
    import { abdeckungsPfad, anzahlCurricula, fassungTitel, sichtbareFassungen } from '$lib/curriculum_baender.js'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'
    import CurriculumYamlImportDialog from '$lib/components/CurriculumYamlImportDialog.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import ListenZeile from '$lib/components/ListenZeile.svelte'

    let { subjectId = null, subjectFachCode = null, showNewButton = true } = $props()

    let uebersicht = $state(null)
    let importOffen = $state(false)
    let loading = $state(true)
    let error = $state(null)

    // Mitglied der Fachschaft (oder Admin): darf Curricula anlegen.
    const canEditSubject = $derived.by(() => {
        if (!subjectId || !$user) return false
        if ($user.roles?.includes('admin')) return true
        if ($user.roles?.includes('teacher')) {
            return $myTeachingGroups.some(g => g.subject_id === subjectId)
                || $myGroups.some(g => g.type === 'subject_department' && g.subject_id === subjectId)
        }
        return false
    })
    const lehrkraft = $derived(!!$user?.roles?.includes('teacher'))

    $effect(() => {
        if (!subjectId) return
        let abgebrochen = false
        loading = true
        error = null
        getCurriculaNachBaendern(subjectId)
            .then((u) => { if (!abgebrochen) uebersicht = u })
            .catch((e) => { if (!abgebrochen) error = e.message })
            .finally(() => { if (!abgebrochen) loading = false })
        return () => { abgebrochen = true }
    })

    const fassungen = $derived(sichtbareFassungen(uebersicht, { leereBaender: canEditSubject }))
    const leer = $derived(fassungen.length === 0 && !(uebersicht?.ohne_fassung?.length))

    const link = 'text-xs text-light-bl dark:text-dark-bl hover:underline'
</script>

{#snippet zeile(curr)}
    <!-- Rahmen und Marken gemeinsam mit den Jahresverlaufsplänen (ListenZeile, 0.59).
         Entwurf (0.45): seit 0.52 für alle Lehrkräfte, „ersetzt …“ steht in der Zeile (AZ, F1).
         „Bearbeitbar“ seit 0.45 vom Backend (`darf_schreiben`, Curriculum-Regel samt Fachvorsitz). -->
    <ListenZeile
        href={`/knowledge/curriculum/${curr.id}`}
        titel={curr.title}
        zusatz={` · Klasse ${curr.jahrgangsstufe || '?'}`
            + (curr.ersetzt ? ` · ersetzt „${curr.ersetzt.title ?? 'veröffentlichtes Curriculum'}“` : '')
            + (curr.status === 'draft' && curr.zuletzt_geaendert
                ? ` · zuletzt geändert ${new Date(curr.zuletzt_geaendert).toLocaleDateString('de-DE')}` : '')}
        entwurf={curr.status === 'draft'}
        entwurfHinweis="Noch nicht veröffentlicht — lesen können ihn alle Lehrkräfte, bearbeiten die Fachschaft"
        bearbeitbar={!!curr.darf_schreiben}
    />
{/snippet}

{#snippet fassungInhalt(f)}
    <div class="space-y-4">
        {#each f.baender as b (b.schluessel)}
            <div>
                <div class="flex items-baseline justify-between gap-2 mb-1.5">
                    <h4 class="text-sm font-semibold text-light-tx dark:text-dark-tx">{b.schluessel}</h4>
                    {#if lehrkraft && b.curricula.length > 0}
                        <a href={abdeckungsPfad({ fachId: subjectId, fassung: f.bp_version, band: b.schluessel })}
                           class={link}>
                            IK-Abdeckung im Band
                        </a>
                    {/if}
                </div>
                {#if b.curricula.length > 0}
                    <div class="space-y-1.5">
                        {#each b.curricula as curr (curr.id)}
                            {@render zeile(curr)}
                        {/each}
                    </div>
                {:else}
                    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">noch kein Curriculum</p>
                {/if}
            </div>
        {/each}
        {#if f.nicht_zugeordnet.length > 0}
            <div>
                <h4 class="text-sm font-semibold text-light-tx dark:text-dark-tx mb-0.5">Band nicht zugeordnet</h4>
                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mb-1.5">
                    Zu diesen Stufen gibt es mehrere Bänder. Im Editor lässt sich das Band wählen.
                </p>
                <div class="space-y-1.5">
                    {#each f.nicht_zugeordnet as curr (curr.id)}
                        {@render zeile(curr)}
                    {/each}
                </div>
            </div>
        {/if}
    </div>
{/snippet}

<div class="space-y-4">
    {#if error}
        <ErrorBanner message={error} />
    {/if}

    {#if loading}
        <LoadingBanner message="Curricula werden geladen…" />
    {:else if leer}
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
            Keine Curricula für dieses Fach verfügbar.
        </p>
    {:else}
        {#each fassungen as f (f.bp_version)}
            <!-- Jede Fassung einklappbar; frühere zu Beginn eingeklappt. -->
            <details class="group rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-3" open={f.art !== 'aelter'}>
                <summary class="cursor-pointer flex items-baseline gap-2">
                    <span class="text-base font-semibold {f.art === 'aelter' ? 'text-light-tx-2 dark:text-dark-tx-2' : 'text-light-tx dark:text-dark-tx'}">
                        {fassungTitel(f)}
                    </span>
                    <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">({anzahlCurricula(f)})</span>
                </summary>
                <div class="mt-3">
                    {#if lehrkraft && anzahlCurricula(f) > 0}
                        <!-- Schritt 9: Die PK gelten für die ganze Fassung, nicht für ein Band. -->
                        <div class="mb-3 text-right">
                            <a href={abdeckungsPfad({ fachId: subjectId, fassung: f.bp_version })} class={link}>
                                PK-Abdeckung der Fassung
                            </a>
                        </div>
                    {/if}
                    {@render fassungInhalt(f)}
                </div>
            </details>
        {/each}
        {#if uebersicht?.ohne_fassung?.length}
            <section>
                <h3 class="text-sm font-semibold text-light-tx-2 dark:text-dark-tx-2 mb-1.5">Ohne Bildungsplan-Fassung</h3>
                <div class="space-y-1.5">
                    {#each uebersicht.ohne_fassung as curr (curr.id)}
                        {@render zeile(curr)}
                    {/each}
                </div>
            </section>
        {/if}
    {/if}

    <!-- "Neues Curriculum anlegen"-Button für Fachschaftsmitglieder / Admins -->
    {#if showNewButton && canEditSubject}
        <div class="pt-2">
            <a
                href={`/knowledge/curriculum/new${subjectFachCode ? `?fach_code=${encodeURIComponent(subjectFachCode)}` : ''}`}
                class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium
                       border border-light-ui-3 dark:border-dark-ui-3
                       text-light-tx-2 dark:text-dark-tx-2
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
            >
                + Neues Curriculum
            </a>
            <!-- 0.56 (BA): legt immer einen Entwurf an; Rechte prüft das Backend (Fachschaft). -->
            <button
                type="button"
                onclick={() => (importOffen = true)}
                class="ml-2 inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium
                       border border-light-ui-3 dark:border-dark-ui-3
                       text-light-tx-2 dark:text-dark-tx-2
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
            >
                Aus YAML importieren
            </button>
        </div>
    {/if}
    {#if importOffen}
        <CurriculumYamlImportDialog onClose={() => (importOffen = false)} />
    {/if}
</div>
